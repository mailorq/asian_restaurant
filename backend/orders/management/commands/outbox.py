"""
operator handling of outbox rows the relay cannot publish

a domain event is never dropped automatically, so a row that keeps failing stays pending and
needs a human: either the cause is fixed and the row is retried, or the row is closed on purpose
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from orders.management.commands.publish_outbox import STUCK_ATTEMPTS
from orders.models import OrderOutbox

log = logging.getLogger(__name__)

ERROR_PREVIEW = 160


def _stuck():
    return OrderOutbox.objects.filter(
        status=OrderOutbox.Status.PENDING, attempts__gte=STUCK_ATTEMPTS
    ).order_by("created_at")


class Command(BaseCommand):
    help = "Lists outbox rows the relay cannot publish, retries them, or closes them."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--list", action="store_true")
        parser.add_argument("--retry", nargs="+", type=int, default=[], metavar="ID")
        parser.add_argument("--discard", nargs="+", type=int, default=[], metavar="ID")
        parser.add_argument("--yes", action="store_true", help="required to close a row")
        parser.add_argument("--reason", default="", help="why the row will never be published")
        parser.add_argument("--operator", default="", help="who is taking the action")

    def handle(self, *args, **options) -> None:
        retry, discard = options["retry"], options["discard"]
        if retry and discard:
            raise CommandError("retry and discard cannot run together")
        if discard:
            if not options["yes"]:
                raise CommandError("closing a row needs --yes")
            if not options["reason"].strip():
                raise CommandError("closing a row needs --reason")
        if not (retry or discard):
            self._list()
        elif retry:
            self._retry(retry)
        else:
            self._discard(discard, options["reason"], options["operator"])

    def _list(self) -> None:
        rows = list(_stuck())
        self.stdout.write(f"{len(rows)} row(s) past {STUCK_ATTEMPTS} attempts")
        now = timezone.now()
        for row in rows:
            age = int((now - row.created_at).total_seconds())
            self.stdout.write(
                f"  #{row.pk} {row.event_type} -> {row.routing_key} | "
                f"attempts={row.attempts} age={age}s"
            )
            if row.last_error:
                self.stdout.write(f"    {row.last_error[:ERROR_PREVIEW]}")

    def _retry(self, ids) -> None:
        # the lease is cleared too, so a row held by a worker that died is claimable again
        updated = OrderOutbox.objects.filter(
            pk__in=ids, status=OrderOutbox.Status.PENDING
        ).update(attempts=0, next_attempt_at=None, locked_until=None, locked_by="", lease_token=None)
        for row_id in ids:
            log.info("outbox row queued for another attempt", extra={"outbox_id": row_id})
        self.stdout.write(self.style.SUCCESS(f"{updated} row(s) will be attempted again"))

    def _discard(self, ids, reason: str, operator: str) -> None:
        rows = list(OrderOutbox.objects.filter(pk__in=ids, status=OrderOutbox.Status.PENDING))
        for row in rows:
            log.warning(
                "outbox row closed by an operator",
                extra={"outbox_id": row.pk, "event_id": str(row.event_id),
                       "event_type": row.event_type, "routing_key": row.routing_key,
                       "operator": operator or "unattributed", "reason": reason},
            )
        updated = OrderOutbox.objects.filter(pk__in=[r.pk for r in rows]).update(
            status=OrderOutbox.Status.FAILED,
            last_error=f"closed by {operator or 'unattributed'}: {reason}"[:1000],
            next_attempt_at=None, locked_until=None, locked_by="", lease_token=None,
        )
        self.stdout.write(self.style.SUCCESS(f"{updated} row(s) closed"))
