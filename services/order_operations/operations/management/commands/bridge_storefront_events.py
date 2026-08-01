import datetime as dt
import json
import logging
from decimal import Decimal

import pika
from django.conf import settings
from django.core.management.base import BaseCommand
from event_contracts import EVENT_ORDER_CREATED, EVENT_ORDER_STATUS_CHANGED, parse_event

from operations import messaging

log = logging.getLogger(__name__)

# temporary adapter: storefront still emits legacy `order.*`; remove once storefront
# publishes versioned envelopes natively. it spans two vhosts — consumes storefront,
# publishes operations — so it never shares a connection or credentials with either app.
STOREFRONT_EXCHANGE = "orders"
BRIDGE_QUEUE = "operations.bridge.storefront"
BRIDGE_DLX = "operations.bridge.dlx"
BRIDGE_DLQ = "operations.bridge.storefront.dlq"
BRIDGE_RETRY_EXCHANGE = "operations.bridge.retry"
BRIDGE_RETRY_QUEUE = "operations.bridge.storefront.retry"
BRIDGE_REQUEUE_EXCHANGE = "operations.bridge.requeue"
BRIDGE_RETRY_TTL_MS = 5000
BRIDGE_MAX_RETRIES = 5
RETRY_HEADER = "x-bridge-retries"

LEGACY_TO_VERSIONED = {
    "order.created": EVENT_ORDER_CREATED,
    "order.status_changed": EVENT_ORDER_STATUS_CHANGED,
}


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def declare_bridge_topology(channel) -> None:
    # storefront owns the `orders` exchange; the bridge only binds to it (read perm),
    # so it must not declare it here
    channel.exchange_declare(exchange=BRIDGE_DLX, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=BRIDGE_RETRY_EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=BRIDGE_REQUEUE_EXCHANGE, exchange_type="topic", durable=True)

    channel.queue_declare(queue=BRIDGE_DLQ, durable=True)
    channel.queue_bind(queue=BRIDGE_DLQ, exchange=BRIDGE_DLX, routing_key="#")

    channel.queue_declare(
        queue=BRIDGE_RETRY_QUEUE,
        durable=True,
        arguments={"x-message-ttl": BRIDGE_RETRY_TTL_MS, "x-dead-letter-exchange": BRIDGE_REQUEUE_EXCHANGE},
    )
    channel.queue_bind(queue=BRIDGE_RETRY_QUEUE, exchange=BRIDGE_RETRY_EXCHANGE, routing_key="#")

    channel.queue_declare(queue=BRIDGE_QUEUE, durable=True, arguments={"x-dead-letter-exchange": BRIDGE_DLX})
    channel.queue_bind(queue=BRIDGE_QUEUE, exchange=STOREFRONT_EXCHANGE, routing_key="order.*")
    channel.queue_bind(queue=BRIDGE_QUEUE, exchange=BRIDGE_REQUEUE_EXCHANGE, routing_key="#")


def _map_data(event_type: str, legacy: dict) -> dict:
    if event_type == EVENT_ORDER_CREATED:
        items = []
        for item in legacy.get("items", []):
            quantity = int(item.get("quantity", 0))
            unit_price = str(item.get("unit_price", "0"))
            line_total = item.get("line_total")
            if line_total is None:
                line_total = Decimal(unit_price) * quantity
            items.append(
                {
                    "source_product_id": _safe_int(item.get("product_id")),
                    "product_code": item.get("product_code", ""),
                    "name": item.get("name", ""),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": str(line_total),
                }
            )
        return {
            "order_id": legacy["order_id"],
            "customer_id": legacy.get("user_id", 0),
            "status": legacy.get("status", "created"),
            "total": str(legacy.get("total", "0")),
            "recipient_name": legacy.get("recipient_name", ""),
            "phone": legacy.get("phone", ""),
            "address": legacy.get("address", ""),
            "address_verified": legacy.get("address_verified", False),
            "items": items,
        }
    return {
        "order_id": legacy["order_id"],
        "status": legacy.get("status", ""),
        "from_status": legacy.get("from_status", ""),
    }


ORIGIN_PRODUCER = "storefront"
RELAYED_BY = "storefront-bridge"


def build_envelope(properties, event_type: str, legacy: dict) -> dict:
    headers = properties.headers or {}
    return {
        "event_id": headers.get("event_id") or properties.message_id,
        "event_type": event_type,
        "schema_version": 1,
        # carry the origin's occurred_at; the bridge is not the source of truth for time
        "occurred_at": headers.get("occurred_at") or dt.datetime.now(dt.UTC).isoformat(),
        "producer": ORIGIN_PRODUCER,
        "relayed_by": RELAYED_BY,
        "aggregate": {
            "type": "order",
            "id": str(legacy["order_id"]),
            "version": _safe_int(headers.get("aggregate_version"), 1),
        },
        "correlation_id": headers.get("correlation_id") or properties.correlation_id,
        "causation_id": None,
        "trace_id": None,
        "data": _map_data(event_type, legacy),
    }


class Command(BaseCommand):
    help = "Bridge legacy storefront order events to versioned operations.events (temporary adapter)."

    def handle(self, *args, **options) -> None:
        consume_conn = pika.BlockingConnection(pika.URLParameters(settings.BRIDGE_CONSUME_URL))
        publish_conn = pika.BlockingConnection(pika.URLParameters(settings.BRIDGE_PUBLISH_URL))
        channel = consume_conn.channel()
        self.publish_channel = publish_conn.channel()
        declare_bridge_topology(channel)
        self.publish_channel.exchange_declare(exchange=messaging.EXCHANGE, exchange_type="topic", durable=True)
        self.publish_channel.confirm_delivery()
        channel.basic_qos(prefetch_count=20)
        channel.basic_consume(queue=BRIDGE_QUEUE, on_message_callback=self._on_message)
        self.stdout.write(self.style.SUCCESS(f"storefront bridge: {BRIDGE_QUEUE} -> {messaging.EXCHANGE}"))
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            consume_conn.close()
            publish_conn.close()

    def _on_message(self, channel, method, properties, body) -> None:
        event_type = LEGACY_TO_VERSIONED.get(properties.type)
        if event_type is None:
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        try:
            legacy = json.loads(body)
            envelope = build_envelope(properties, event_type, legacy)
            parse_event(envelope)
        except Exception:
            log.exception("bridge poison message -> DLQ")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        try:
            # ack the legacy delivery only after the versioned publish is confirmed
            messaging.publish_envelope(
                self.publish_channel, messaging.EXCHANGE, event_type, envelope,
                {"event_id": envelope["event_id"], "x-relayed-by": RELAYED_BY},
            )
        except Exception:
            self._retry(channel, method, properties, body)
            return
        channel.basic_ack(method.delivery_tag)

    def _retry(self, channel, method, properties, body) -> None:
        retries = _safe_int((properties.headers or {}).get(RETRY_HEADER), 0)
        if retries >= BRIDGE_MAX_RETRIES:
            log.warning("bridge retries exhausted -> DLQ")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        headers = {**(properties.headers or {}), RETRY_HEADER: retries + 1}
        try:
            channel.basic_publish(
                exchange=BRIDGE_RETRY_EXCHANGE,
                routing_key=method.routing_key,
                body=body,
                properties=pika.BasicProperties(
                    content_type=properties.content_type or "application/json",
                    delivery_mode=2,
                    message_id=properties.message_id,
                    correlation_id=properties.correlation_id,
                    type=properties.type,
                    headers=headers,
                ),
                mandatory=True,
            )
        except Exception:
            log.exception("bridge retry publish failed; requeueing original")
            channel.basic_nack(method.delivery_tag, requeue=True)
            return
        channel.basic_ack(method.delivery_tag)
