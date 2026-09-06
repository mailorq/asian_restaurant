import json
import logging

import pika
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError
from event_contracts import UnknownEventType, parse_event
from prometheus_client import start_http_server
from pydantic import ValidationError

from operations import dispatch, messaging, projection
from operations.commands import OutcomeMismatch
from operations.jsonlog import describe_error, log_context
from operations.metrics import consumer_connected, projection_events

log = logging.getLogger(__name__)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Command(BaseCommand):
    help = "Shadow-mode consumer: builds operations projections from versioned domain events."

    def handle(self, *args, **options) -> None:
        start_http_server(settings.METRICS_PORT)
        consumer_connected.set(0)
        connection = messaging.connect()
        channel = connection.channel()
        messaging.declare_topology(channel)
        channel.confirm_delivery()
        channel.basic_qos(prefetch_count=10)
        for queue in messaging.CONSUMED_QUEUES:
            channel.basic_consume(queue=queue, on_message_callback=self._on_message)
        consumer_connected.set(1)  # topology declared and consuming; readiness is now true
        self.stdout.write(
            self.style.SUCCESS(
                f"operations consumer listening on {', '.join(messaging.CONSUMED_QUEUES)}; "
                f"metrics on :{settings.METRICS_PORT}"
            )
        )
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            consumer_connected.set(0)
            connection.close()

    def _on_message(self, channel, method, properties, body) -> None:
        retries = _safe_int((properties.headers or {}).get("x-retries"), 0)
        try:
            envelope, data = parse_event(json.loads(body))
        except (json.JSONDecodeError, ValueError, ValidationError, UnknownEventType) as exc:
            # the rejected value is the event body, which carries customer data
            log.warning("operations poison message -> DLQ", extra={"message_id": getattr(properties, "message_id", None), "routing_key": method.routing_key, "error_shape": describe_error(exc)})
            channel.basic_nack(method.delivery_tag, requeue=False)
            return

        with log_context(
            event_id=str(envelope.event_id),
            correlation_id=str(envelope.correlation_id),
            causation_id=str(envelope.causation_id) if envelope.causation_id else None,
            event_type=envelope.event_type,
        ):
            self._apply(channel, method, properties, body, envelope, data, retries)

    def _apply(self, channel, method, properties, body, envelope, data, retries: int) -> None:
        try:
            dispatch.handle(envelope, data)
        except projection.ProjectionConflict as exc:
            log.warning(
                "operations projection conflict -> DLQ",
                extra={"event_id": str(envelope.event_id), "event_type": envelope.event_type,
                       "aggregate_id": exc.aggregate_id, "version": exc.version},
            )
            projection_events.labels(envelope.event_type, "conflict").inc()
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        except OutcomeMismatch:
            log.warning("operations outcome does not match its command -> DLQ")
            projection_events.labels(envelope.event_type, "outcome_mismatch").inc()
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        except projection.SnapshotProtocolError:
            log.warning("operations snapshot protocol violation -> DLQ")
            projection_events.labels(envelope.event_type, "snapshot_protocol").inc()
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        except projection.OutOfOrder:
            projection_events.labels(envelope.event_type, "out_of_order").inc()
            self._retry(channel, method, properties, body, retries)
            return
        except DatabaseError:
            self._retry(channel, method, properties, body, retries)
            return
        channel.basic_ack(method.delivery_tag)

    def _retry(self, channel, method, properties, body, retries: int) -> None:
        if retries >= messaging.MAX_RETRIES:
            log.warning("operations retries exhausted -> DLQ")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        headers = {**(properties.headers or {}), "x-retries": retries + 1}
        try:
            channel.basic_publish(
                exchange=messaging.RETRY_EXCHANGE,
                routing_key=method.routing_key,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=properties.message_id,
                    correlation_id=properties.correlation_id,
                    headers=headers,
                ),
                mandatory=True,
            )
        except Exception:
            log.exception("operations retry publish failed; requeueing original")
            channel.basic_nack(method.delivery_tag, requeue=True)
            return
        channel.basic_ack(method.delivery_tag)
