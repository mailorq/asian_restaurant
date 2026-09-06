"""
relay for the command outbox: publishes transition requests to the storefront vhost

it holds `configure=^$` there and cannot create anything, so the storefront consumer must have
declared the topology first. a missing exchange or binding is therefore a readiness problem and
never counts as a failed dispatch
"""

import logging
import random
import socket
import time
from datetime import timedelta

import pika
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from event_contracts import EVENT_ORDER_TRANSITION_REQUESTED, parse_event
from pika.exceptions import AMQPError, ChannelClosedByBroker, UnroutableError
from prometheus_client import start_http_server

from operations import commands as command_service
from operations import messaging
from operations.commands import ClaimResult
from operations.jsonlog import log_context
from operations.metrics import (
    command_dispatch_total,
    command_outbox_oldest_pending_age_seconds,
    command_relay_connected,
)
from operations.models import OperationCommand, OperationsOutbox

log = logging.getLogger(__name__)

BATCH = 50
LEASE = timedelta(seconds=60)
BACKOFF_BASE_SECONDS = 2
BACKOFF_MAX_SECONDS = 64
MAX_ATTEMPTS = 5
# a returned publish means the topology is missing, which an operator repairs in minutes. an
# exponential backoff is the wrong shape for that, and an unbounded one leaves the command open
# forever, so these retries are rare, fixed and counted
TOPOLOGY_RETRY_SECONDS = 20
TOPOLOGY_MAX_ATTEMPTS = 8
SWEEP_INTERVAL_SECONDS = 5
AGGREGATE_TYPE = "order"


def _backoff(attempts: int) -> timedelta:
    base = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** min(attempts, 10)))
    return timedelta(seconds=base + random.uniform(0, base * 0.25))


def _envelope(row: OperationsOutbox) -> dict:
    return {
        "event_id": str(row.event_id),
        "event_type": row.event_type,
        "schema_version": row.schema_version,
        "occurred_at": row.created_at.isoformat(),
        "producer": row.producer,
        "aggregate": {
            "type": AGGREGATE_TYPE,
            "id": row.aggregate_id,
            "version": row.aggregate_version,
        },
        "correlation_id": str(row.correlation_id),
        "causation_id": str(row.causation_id) if row.causation_id else None,
        "data": row.payload,
    }


class Command(BaseCommand):
    help = "Leased relay: publishes pending transition commands to the storefront command exchange."

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._connection = None
        self._channel = None
        self._next_sweep = 0.0

    def add_arguments(self, parser) -> None:
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=float, default=1.0)

    def handle(self, *args, **options) -> None:
        if not settings.COMMANDS_RABBITMQ_URL:
            raise CommandError(
                "OPERATIONS_COMMANDS_RABBITMQ_URL is required; without it the relay would fall "
                "back to the operations vhost and publish commands nobody consumes"
            )
        worker_id = f"{socket.gethostname()}:{id(self)}"
        start_http_server(settings.METRICS_PORT)
        command_relay_connected.set(0)

        if not options["loop"]:
            self.stdout.write(self.style.SUCCESS(f"dispatched {self._drain(worker_id)} command(s)"))
            self._close()
            return

        self.stdout.write(self.style.SUCCESS(f"command relay {worker_id} started"))
        try:
            while True:
                self._drain(worker_id)
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            pass
        finally:
            self._close()

    # transport
    def _open(self):
        if self._channel is not None and self._channel.is_open:
            return self._channel
        if self._connection is None or not self._connection.is_open:
            self._connection = pika.BlockingConnection(
                pika.URLParameters(settings.COMMANDS_RABBITMQ_URL)
            )
        self._channel = self._connection.channel()
        self._channel.confirm_delivery()
        command_relay_connected.set(1)
        return self._channel

    def _drop_channel(self) -> None:
        # the broker closes the channel on 404 and 403; an unroutable publish leaves it open
        channel, self._channel = self._channel, None
        if channel is not None and channel.is_open:
            try:
                channel.close()
            except AMQPError:
                pass

    def _drop_connection(self) -> None:
        self._channel = None
        if self._connection is not None:
            try:
                self._connection.close()
            except AMQPError:
                pass
        self._connection = None
        command_relay_connected.set(0)

    def _close(self) -> None:
        self._drop_connection()

    # work
    def _eligible(self) -> list[int]:
        now = timezone.now()
        return list(
            OperationsOutbox.objects.filter(
                status=OperationsOutbox.Status.PENDING,
                event_type=EVENT_ORDER_TRANSITION_REQUESTED,
            )
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
            .order_by("created_at")
            .values_list("pk", flat=True)[:BATCH]
        )

    def _sweep_due(self) -> bool:
        now = time.monotonic()
        if now < self._next_sweep:
            return False
        # jittered so two replicas do not sweep the same rows in lockstep
        self._next_sweep = now + SWEEP_INTERVAL_SECONDS * random.uniform(0.8, 1.2)
        return True

    def _drain(self, worker_id: str) -> int:
        if self._sweep_due():
            for result, count in command_service.sweep_expired().items():
                if count:
                    command_dispatch_total.labels(result).inc(count)
        dispatched = 0
        for row_id in self._eligible():
            result, row = command_service.claim_or_expire(row_id, worker=worker_id, lease=LEASE)
            if result is ClaimResult.EXPIRED:
                command_dispatch_total.labels("expired").inc()
                continue
            if row is None:
                continue  # another worker holds it, or it is already resolved
            if self._publish_one(row):
                dispatched += 1
        self._report_backlog()
        return dispatched

    def _report_backlog(self) -> None:
        oldest = (
            OperationsOutbox.objects.filter(
                status=OperationsOutbox.Status.PENDING,
                event_type=EVENT_ORDER_TRANSITION_REQUESTED,
            )
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        command_outbox_oldest_pending_age_seconds.set(
            (timezone.now() - oldest).total_seconds() if oldest else 0.0
        )

    def _publish_one(self, row: OperationsOutbox) -> bool:
        with log_context(event_id=str(row.event_id), correlation_id=str(row.correlation_id),
                         causation_id=str(row.causation_id) if row.causation_id else None):
            return self._publish_held(row)

    def _publish_held(self, row: OperationsOutbox) -> bool:
        envelope = _envelope(row)
        try:
            parse_event(envelope)
        except Exception as exc:
            # deterministic: no later attempt can make this row valid
            log.exception("command envelope violates the contract", extra={"event_id": str(row.event_id)})
            command_service.reject_undeliverable(
                row, code=command_service.CODE_INVALID_PAYLOAD, detail=str(exc)[:1000]
            )
            command_dispatch_total.labels("invalid").inc()
            return False

        try:
            messaging.publish_envelope(
                self._open(), messaging.COMMANDS_EXCHANGE, row.routing_key, envelope
            )
        except UnroutableError as exc:
            self._drop_channel()
            self._undeliverable(row, exc)
            return False
        except ChannelClosedByBroker as exc:
            # the broker can close a channel after accepting a message, so unlike a returned
            # publish this is not proof that nothing was delivered
            self._drop_channel()
            self._defer(row, exc)
            return False
        except (AMQPError, OSError) as exc:
            self._drop_connection()
            self._defer(row, exc)
            return False
        except Exception as exc:  # pragma: no cover - defensive, keeps the loop alive
            log.exception("command publish failed")
            self._defer(row, exc)
            return False

        if not command_service.confirm_dispatch(row):
            # an outcome settled the row, or a newer worker holds the lease
            command_dispatch_total.labels("superseded").inc()
            return False
        command_dispatch_total.labels("dispatched").inc()
        return True

    def _undeliverable(self, row: OperationsOutbox, exc: Exception) -> None:
        """the broker returned the message: this attempt provably reached no queue"""
        attempts = row.attempts + 1
        log.warning("command topology not ready: %s", exc, extra={"attempts": attempts})
        if attempts < TOPOLOGY_MAX_ATTEMPTS:
            if command_service.schedule_retry(
                row, backoff=timedelta(seconds=TOPOLOGY_RETRY_SECONDS), error=str(exc)[:1000]
            ):
                command_dispatch_total.labels("topology").inc()
            else:
                command_dispatch_total.labels("superseded").inc()
            return
        if command_service.reject_undeliverable(
            row, code=command_service.CODE_UNDELIVERABLE, detail=str(exc)[:1000]
        ) is None:
            command_dispatch_total.labels("superseded").inc()
            return
        command_dispatch_total.labels("undeliverable").inc()
        log.error(
            "command never reached a queue, closing it", extra={"attempts": attempts,
            "event_id": str(row.event_id), "correlation_id": str(row.correlation_id)},
        )

    def _defer(self, row: OperationsOutbox, exc: Exception) -> None:
        attempts = row.attempts + 1
        if attempts < MAX_ATTEMPTS:
            if command_service.schedule_retry(row, backoff=_backoff(attempts),
                                              error=str(exc)[:1000]):
                command_dispatch_total.labels("retried").inc()
            else:
                command_dispatch_total.labels("superseded").inc()
            return

        if not command_service.abandon_row(row, error=str(exc)[:1000]):
            command_dispatch_total.labels("superseded").inc()
            return
        command_dispatch_total.labels("abandoned").inc()
        log.error(
            "command abandoned after %s publish attempts", attempts,
            extra={"event_id": str(row.event_id), "correlation_id": str(row.correlation_id),
                   "attempts": attempts, "reason": type(exc).__name__},
        )
        if row.command_id is None:
            return
        command = OperationCommand.objects.filter(pk=row.command_id).first()
        if command is not None:
            # delivery is unknown, so the command stays open for reconciliation
            command_service.mark_dispatch_failed(command)
            command_dispatch_total.labels("dispatch_failed").inc()
