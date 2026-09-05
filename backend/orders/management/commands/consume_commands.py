"""
storefront consumer for operations transition commands

owns the command topology: the operations publisher holds `configure=^$` and can neither
declare nor repair it, so this process must create it before it starts consuming
"""

import json
import logging
import os

import pika
from django.core.management.base import BaseCommand
from django.db import DatabaseError, InterfaceError, connections
from event_contracts import EVENT_ORDER_TRANSITION_REQUESTED, UnknownEventType, parse_event
from pydantic import ValidationError

from config.jsonlog import log_context
from config.metrics import commands_applied_total, commands_consumer_connected
from orders import command_messaging as topology
from orders import messaging
from orders.commands import Outcome, apply_transition_command

try:
    from prometheus_client import start_http_server
except ImportError:  # pragma: no cover
    start_http_server = None

log = logging.getLogger(__name__)

RETRY_HEADER = "x-retries"
PREFETCH = 10


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _label(outcome: Outcome) -> str:
    if outcome.replayed:
        return "replayed"
    return "rejected" if outcome.rejected else "succeeded"


class Command(BaseCommand):
    help = "Applies operations transition commands; the storefront stays the sole writer of order state."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--metrics-port", type=int, default=int(os.environ.get("COMMANDS_METRICS_PORT", "0"))
        )

    def handle(self, *args, **options) -> None:
        if options["metrics_port"] and start_http_server is not None:
            start_http_server(options["metrics_port"])
        commands_consumer_connected.set(0)
        connection = messaging.connect()
        channel = connection.channel()
        topology.declare_topology(channel)
        channel.confirm_delivery()
        channel.basic_qos(prefetch_count=PREFETCH)
        channel.basic_consume(queue=topology.QUEUE, on_message_callback=self._on_message)
        commands_consumer_connected.set(1)  # topology declared and consuming; readiness is now true
        self.stdout.write(self.style.SUCCESS(f"command consumer listening on {topology.QUEUE}"))
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            commands_consumer_connected.set(0)
            connection.close()

    def _on_message(self, channel, method, properties, body) -> None:
        retries = _safe_int((properties.headers or {}).get(RETRY_HEADER), 0)
        try:
            envelope, data = parse_event(json.loads(body))
        except (json.JSONDecodeError, ValueError, ValidationError, UnknownEventType):
            log.exception("command poison message -> DLQ",
                          extra={"message_id": getattr(properties, "message_id", None)})
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        with log_context(
            event_id=str(envelope.event_id),
            correlation_id=str(envelope.correlation_id),
            causation_id=str(envelope.causation_id) if envelope.causation_id else None,
            event_type=envelope.event_type,
            command_id=str(data.command_id),
        ):
            self._apply(channel, method, properties, body, envelope, data, retries)

    def _apply(self, channel, method, properties, body, envelope, data, retries: int) -> None:
        if envelope.event_type != EVENT_ORDER_TRANSITION_REQUESTED:
            # the queue binds one routing key, so anything else here is a topology mistake
            log.warning("unexpected event on the command queue -> DLQ")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        try:
            outcome = apply_transition_command(
                data, request_event_id=envelope.event_id, correlation_id=envelope.correlation_id
            )
        except (DatabaseError, InterfaceError):
            connections.close_all()
            self._retry(channel, method, properties, body, retries)
            return
        except Exception:
            log.exception("command application failed -> DLQ", extra={"order_id": data.order_id})
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        commands_applied_total.labels(_label(outcome)).inc()
        channel.basic_ack(method.delivery_tag)

    def _retry(self, channel, method, properties, body, retries: int) -> None:
        if retries >= topology.MAX_RETRIES:
            log.warning("command retries exhausted -> DLQ")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        headers = {**(properties.headers or {}), RETRY_HEADER: retries + 1}
        try:
            channel.basic_publish(
                exchange=topology.RETRY_EXCHANGE,
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
            log.exception("command retry publish failed; requeueing original")
            channel.basic_nack(method.delivery_tag, requeue=True)
            return
        channel.basic_ack(method.delivery_tag)
