import datetime as dt
import json
import logging

from django.core.management.base import BaseCommand
from event_contracts import EVENT_ORDER_CREATED, EVENT_ORDER_STATUS_CHANGED

from operations import messaging

log = logging.getLogger(__name__)

# Temporary adapter: storefront still emits legacy `order.*`; this bridge maps them
# to versioned envelopes on operations.events. Removed once storefront publishes
# versioned events natively.
STOREFRONT_EXCHANGE = "orders"
BRIDGE_QUEUE = "operations.bridge.storefront"
LEGACY_TO_VERSIONED = {
    "order.created": EVENT_ORDER_CREATED,
    "order.status_changed": EVENT_ORDER_STATUS_CHANGED,
}


def _map_data(event_type: str, legacy: dict) -> dict:
    if event_type == EVENT_ORDER_CREATED:
        items = []
        for item in legacy.get("items", []):
            unit_price = str(item.get("unit_price", "0"))
            quantity = int(item.get("quantity", 0))
            items.append(
                {
                    "product_code": str(item.get("product_id", "")),
                    "name": item.get("name", ""),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": str(float(unit_price) * quantity),
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


class Command(BaseCommand):
    help = "Bridge legacy storefront order events to versioned operations.events (temporary adapter)."

    def handle(self, *args, **options) -> None:
        connection = messaging.connect()
        channel = connection.channel()
        channel.exchange_declare(exchange=STOREFRONT_EXCHANGE, exchange_type="topic", durable=True)
        messaging.declare_topology(channel)
        channel.queue_declare(queue=BRIDGE_QUEUE, durable=True)
        channel.queue_bind(queue=BRIDGE_QUEUE, exchange=STOREFRONT_EXCHANGE, routing_key="order.*")
        channel.confirm_delivery()
        channel.basic_qos(prefetch_count=20)
        channel.basic_consume(queue=BRIDGE_QUEUE, on_message_callback=self._on_message)
        self.stdout.write(self.style.SUCCESS(f"storefront bridge listening on {BRIDGE_QUEUE}"))
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            connection.close()

    def _on_message(self, channel, method, properties, body) -> None:
        headers = properties.headers or {}
        event_type = LEGACY_TO_VERSIONED.get(properties.type)
        if event_type is None:
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        try:
            legacy = json.loads(body)
            envelope = {
                "event_id": headers.get("event_id") or properties.message_id,
                "event_type": event_type,
                "schema_version": 1,
                "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
                "producer": "storefront-bridge",
                "aggregate": {
                    "type": "order",
                    "id": str(legacy["order_id"]),
                    "version": int(headers.get("aggregate_version") or 1),
                },
                "correlation_id": headers.get("correlation_id") or properties.correlation_id,
                "causation_id": None,
                "trace_id": None,
                "data": _map_data(event_type, legacy),
            }
            messaging.publish_envelope(
                channel, messaging.EXCHANGE, event_type, envelope, {"event_id": envelope["event_id"]}
            )
        except Exception:
            log.exception("bridge failed; requeue")
            channel.basic_nack(method.delivery_tag, requeue=True)
            return
        channel.basic_ack(method.delivery_tag)
