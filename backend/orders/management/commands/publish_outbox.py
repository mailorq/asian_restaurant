import os
import random
import socket
import time
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from orders import messaging
from orders.models import OrderOutbox

try:
    from prometheus_client import Gauge, start_http_server
except ImportError:  # pragma: no cover
    Gauge = None
    start_http_server = None

BATCH = 50
LEASE_SECONDS = 60
BACKOFF_BASE_SECONDS = 2
BACKOFF_MAX_SECONDS = 300


def _backoff_seconds(attempts: int) -> float:
    """Exponential backoff (capped) with additive jitter."""
    base = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** min(attempts, 10)))
    return base + random.uniform(0, base * 0.25)


def _held(row: OrderOutbox) -> dict | None:
    """
    filter matching the live lease this worker holds, or None when it holds none

    null token is not a lease: `lease_token=None` compiles to IS NULL and would match every
    unclaimed row
    """
    if row.lease_token is None:
        return None
    return dict(
        pk=row.pk, lease_token=row.lease_token, status=OrderOutbox.Status.PENDING,
        locked_until__gt=timezone.now(),
    )


def _headers(row: OrderOutbox) -> dict:
    return {
        "event_id": str(row.event_id),
        "correlation_id": str(row.correlation_id),
        "causation_id": str(row.causation_id) if row.causation_id else None,
        "schema_version": row.schema_version,
        "aggregate_version": row.aggregate_version,
        # domain occurred_at travels with the event so downstream never re-times it
        "occurred_at": row.created_at.isoformat(),
        "snapshot": row.snapshot,
        "snapshot_run_id": row.snapshot_run_id or None,
    }


class Command(BaseCommand):
    help = "Leased at-least-once outbox relay: publishes pending order events to RabbitMQ."

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._publisher = messaging.Publisher()

    def add_arguments(self, parser) -> None:
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=float, default=1.0)
        parser.add_argument(
            "--metrics-port", type=int, default=int(os.environ.get("OUTBOX_METRICS_PORT", "0"))
        )

    def handle(self, *args, **options) -> None:
        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        gauge = None
        if options["metrics_port"] and start_http_server is not None:
            start_http_server(options["metrics_port"])
            gauge = Gauge("outbox_oldest_pending_age_seconds", "age of the oldest pending outbox event")

        self._converge_topology()

        try:
            if options["loop"]:
                self.stdout.write(self.style.SUCCESS(f"outbox relay {worker_id} started"))
                while True:
                    self._drain(worker_id, gauge)
                    time.sleep(options["interval"])
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"published {self._drain(worker_id, gauge)} event(s)")
                )
        finally:
            self._publisher.close()

    def _converge_topology(self) -> None:
        conn = messaging.connect()
        try:
            channel = conn.channel()
            messaging.declare_topology(channel)
            messaging.converge_legacy_binding(channel)
        finally:
            conn.close()

    def _claim(self, worker_id: str) -> list[OrderOutbox]:
        now = timezone.now()
        eligible = (
            Q(status=OrderOutbox.Status.PENDING)
            & (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            & (Q(locked_until__isnull=True) | Q(locked_until__lt=now))
        )
        with transaction.atomic():
            rows = list(
                OrderOutbox.objects.select_for_update(skip_locked=True)
                .filter(eligible)
                .order_by("created_at")[:BATCH]
            )
            if rows:
                # one token per claim: a re-claim mints a new one, so the previous holder is
                # fenced off that row while keeping its own other rows
                token = uuid.uuid4()
                locked_until = now + timedelta(seconds=LEASE_SECONDS)
                OrderOutbox.objects.filter(pk__in=[r.pk for r in rows]).update(
                    locked_until=locked_until, locked_by=worker_id, lease_token=token
                )
                for row in rows:
                    row.lease_token, row.locked_until, row.locked_by = token, locked_until, worker_id
        return rows

    def _drain(self, worker_id: str, gauge=None) -> int:
        rows = self._claim(worker_id)
        for row in rows:
            self._publish_one(worker_id, row)
        if gauge is not None:
            oldest = (
                OrderOutbox.objects.filter(status=OrderOutbox.Status.PENDING)
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            gauge.set((timezone.now() - oldest).total_seconds() if oldest else 0.0)
        return len(rows)

    def _publish_one(self, worker_id: str, row: OrderOutbox) -> None:
        held = _held(row)
        if held is None:
            return
        now = timezone.now()
        try:
            self._publisher.publish(row.routing_key, row.event_type, row.payload, _headers(row))
        except Exception as exc:  # broker down / unconfirmed -> keep pending, backoff
            attempts = row.attempts + 1
            OrderOutbox.objects.filter(**held).update(
                attempts=attempts,
                next_attempt_at=now + timedelta(seconds=_backoff_seconds(attempts)),
                last_error=str(exc)[:1000],
                locked_until=None,
                locked_by="",
                lease_token=None,
            )
            self.stderr.write(f"outbox {row.pk} publish failed (attempt {attempts}): {exc}")
            return
        OrderOutbox.objects.filter(**held).update(
            status=OrderOutbox.Status.PUBLISHED,
            published_at=now,
            attempts=row.attempts + 1,
            locked_until=None,
            locked_by="",
            lease_token=None,
        )
