from django.core.management.base import BaseCommand
from django.utils import timezone

from orders import messaging
from orders.models import OrderOutbox


class Command(BaseCommand):
    help = "Publish pending order events to RabbitMQ (transactional outbox relay)."

    def handle(self, *args, **options) -> None:
        pending = OrderOutbox.objects.filter(status=OrderOutbox.Status.PENDING).order_by("created_at")
        published = 0

        for row in pending.iterator():
            try:
                messaging.publish(row.event_type, row.payload)
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

        self.stdout.write(self.style.SUCCESS(f"published {published} event(s)"))
