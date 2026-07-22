import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders import messaging
from orders.models import OrderOutbox


class Command(BaseCommand):
    help = "Relay pending order events from the outbox to RabbitMQ (with publisher confirms)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--loop", action="store_true", help="poll continuously")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **options) -> None:
        if options["loop"]:
            self.stdout.write(self.style.SUCCESS("outbox relay loop started"))
            while True:
                self._drain()
                time.sleep(options["interval"])
        else:
            self.stdout.write(self.style.SUCCESS(f"published {self._drain()} event(s)"))

    def _drain(self) -> int:
        pending = OrderOutbox.objects.filter(status=OrderOutbox.Status.PENDING).order_by("created_at")
        published = 0
        for row in pending.iterator():
            try:
                messaging.publish(
                    routing_key=row.routing_key,
                    event_type=row.event_type,
                    payload=row.payload,
                    headers={
                        "event_id": str(row.event_id),
                        "correlation_id": str(row.correlation_id),
                        "schema_version": row.schema_version,
                        "aggregate_version": row.aggregate_version,
                    },
                )
            except Exception as exc:
                OrderOutbox.objects.filter(pk=row.pk).update(attempts=row.attempts + 1)
                self.stderr.write(f"outbox {row.pk} publish failed: {exc}")
                continue

            OrderOutbox.objects.filter(pk=row.pk).update(
                status=OrderOutbox.Status.PUBLISHED,
                published_at=timezone.now(),
                attempts=row.attempts + 1,
            )
            published += 1
        return published
