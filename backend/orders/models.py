from django.db import models


class OrderOutbox(models.Model):
    """Transactional outbox for lossless order delivery.

    An order and its outbox row are written in the same DB transaction; the
    relay (publish_outbox command) publishes pending rows to RabbitMQ with
    publisher confirms and marks them published. If the broker is unavailable,
    the row stays pending and is retried — the event is never lost.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        PUBLISHED = "published", "Отправлено"

    aggregate_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=64, default="order.created")
    payload = models.JSONField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.aggregate_id} ({self.status})"
