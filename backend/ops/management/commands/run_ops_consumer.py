import json
import logging

from django.core.management.base import BaseCommand
from django.db import DatabaseError

from ops import service
from orders import messaging

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume order events from RabbitMQ and project them into RestaurantOrder (ops runtime)."

    def handle(self, *args, **options) -> None:
        connection = messaging.connect()
        channel = connection.channel()
        messaging.declare_topology(channel)
        channel.basic_qos(prefetch_count=10)
        channel.basic_consume(queue=messaging.OPS_QUEUE, on_message_callback=self._on_message)
        self.stdout.write(self.style.SUCCESS(f"ops consumer listening on {messaging.OPS_QUEUE}"))
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            connection.close()

    def _on_message(self, channel, method, properties, body) -> None:
        headers = properties.headers or {}
        retries = int(headers.get("x-retries", 0) or 0)

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            log.exception("ops poison message (bad json), dead-lettering")
            channel.basic_nack(method.delivery_tag, requeue=False)
            return

        try:
            service.apply_event(
                event_id=headers.get("event_id") or properties.message_id,
                event_type=properties.type,
                aggregate_version=int(headers.get("aggregate_version") or 0),
                payload=payload,
            )
        except (KeyError, TypeError):
            # unusable payload -> poison, straight to the DLQ
            log.exception("ops poison message (bad payload) %s, dead-lettering", headers.get("event_id"))
            channel.basic_nack(method.delivery_tag, requeue=False)
            return
        except (service.OutOfOrder, DatabaseError):
            # transient / out-of-order -> delayed retry, then DLQ once exhausted
            if retries >= messaging.MAX_RETRIES:
                log.warning("ops retries exhausted for %s, dead-lettering", headers.get("event_id"))
                channel.basic_nack(method.delivery_tag, requeue=False)
                return
            messaging._publish(
                channel,
                messaging.RETRY_EXCHANGE,
                method.routing_key,
                properties.type,
                payload,
                {**headers, "x-retries": retries + 1},
            )
            channel.basic_ack(method.delivery_tag)
            return

        channel.basic_ack(method.delivery_tag)
