"""Operations command creation and outcome application.

Operations owns only the command lifecycle; it never writes storefront state. Creation is
idempotent by (actor_id, command_type, target, idempotency_key). An outcome may finalise a
command from any non-terminal state — including timed_out — so a late outcome never leaves a
command that the storefront actually applied stuck as timed_out.
"""

import uuid
from datetime import timedelta
from enum import StrEnum

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from event_contracts import (
    EVENT_ORDER_TRANSITION_REQUESTED,
    OrderTransitionRejectedData,
    OrderTransitionRequestedData,
    OrderTransitionSucceededData,
    TransitionRejectCode,
)

from operations.models import OperationAuditLog, OperationCommand, OperationsOutbox

COMMAND_TYPE_TRANSITION = "orders.transition"
REQUESTED_ROUTING_KEY = "orders.transition.requested"
ACTOR_ROLE = "restaurant_employee"
PRODUCER = "operations"
COMMAND_TTL = timedelta(seconds=30)
IDEMPOTENCY_KEY_MAX = 200


class CommandConflict(Exception):
    """A duplicate idempotency identity carrying a different request."""


class OutcomeMismatch(Exception):
    """An outcome envelope that does not correspond to its referenced command."""


def _request_payload(data: OrderTransitionRequestedData) -> dict:
    # intent compared on a duplicate, without server-minted or per-attempt fields
    return {
        "order_id": data.order_id,
        "expected_status": str(data.expected_status),
        "target_status": str(data.target_status),
        "reason": data.reason,
    }


def create_transition_command(
    *, actor_id: int, actor_authz_version: int, order_id: int, expected_status: str,
    target_status: str, idempotency_key: str, reason: str = "",
) -> tuple[OperationCommand, bool]:
    # validate the dedup key before any write so an oversized key is a controlled 4xx, not a
    # DataError 500 once it reaches the column
    key = (idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key is required")
    if len(key) > IDEMPOTENCY_KEY_MAX:
        raise ValueError(f"idempotency_key must be at most {IDEMPOTENCY_KEY_MAX} characters")
    target = str(order_id)
    command_id = uuid.uuid4()
    request_event_id = uuid.uuid4()
    # stored deadline and the one carried in the message are the same instant
    deadline = timezone.now() + COMMAND_TTL
    # validate the intent against the contract before persisting anything
    data = OrderTransitionRequestedData(
        command_id=command_id, actor_id=actor_id, actor_authz_version=actor_authz_version,
        expires_at=deadline, order_id=order_id, expected_status=expected_status,
        target_status=target_status, reason=reason,
    )
    request = _request_payload(data)

    identity = dict(
        actor_id=actor_id, command_type=COMMAND_TYPE_TRANSITION, target=target, idempotency_key=key
    )
    existing = OperationCommand.objects.filter(**identity).first()
    if existing is not None:
        return _dedup(existing, request), False

    try:
        with transaction.atomic():
            command = OperationCommand.objects.create(
                command_id=command_id, request_event_id=request_event_id, payload=request,
                deadline_at=deadline, **identity,
            )
            OperationsOutbox.objects.create(
                event_id=request_event_id,
                correlation_id=command.correlation_id,
                command=command,
                producer=PRODUCER,
                aggregate_id=target,
                aggregate_version=1,
                routing_key=REQUESTED_ROUTING_KEY,
                event_type=EVENT_ORDER_TRANSITION_REQUESTED,
                payload=data.model_dump(mode="json"),
            )
            OperationAuditLog.objects.create(
                actor_id=str(actor_id), actor_role=ACTOR_ROLE, action=COMMAND_TYPE_TRANSITION,
                target=target, command_id=command_id, result="requested",
            )
    except IntegrityError:
        # a concurrent identical create won the unique(idempotency) race
        existing = OperationCommand.objects.filter(**identity).first()
        if existing is None:
            raise
        return _dedup(existing, request), False
    return command, True


def _dedup(existing: OperationCommand, request: dict) -> OperationCommand:
    if existing.payload != request:
        raise CommandConflict("idempotency_key reused with a different request")
    return existing


def _assert_outcome_matches_intent(command: OperationCommand, data, success: bool) -> None:
    # the outcome must describe the transition this command actually requested, so an outcome for
    # a different target (e.g. created->cancelled) can never finalise a created->confirmed command
    expected = command.payload.get("expected_status")
    target = command.payload.get("target_status")
    if success:
        if str(data.from_status) != expected or str(data.status) != target:
            raise OutcomeMismatch("succeeded outcome does not match the requested transition")
        return
    current = None if data.current_status is None else str(data.current_status)
    if data.reject_code == TransitionRejectCode.stale_status and current == expected:
        raise OutcomeMismatch("stale_status must report a status other than expected_status")
    if data.reject_code == TransitionRejectCode.invalid_transition and current != expected:
        raise OutcomeMismatch("invalid_transition must report the expected_status")


def apply_transition_outcome(data, *, correlation_id, causation_id) -> OperationCommand:
    """Finalise a command from a validated succeeded/rejected outcome; idempotent."""
    if isinstance(data, OrderTransitionSucceededData):
        success = True
    elif isinstance(data, OrderTransitionRejectedData):
        success = False
    else:
        raise OutcomeMismatch("unsupported outcome type")

    command = OperationCommand.objects.filter(command_id=data.command_id).first()
    if command is None:
        raise OutcomeMismatch("no command for outcome command_id")
    if command.command_type != COMMAND_TYPE_TRANSITION:
        raise OutcomeMismatch("command type mismatch")
    if command.target != str(data.order_id) or command.payload.get("order_id") != data.order_id:
        raise OutcomeMismatch("order_id mismatch")
    if str(command.correlation_id) != str(correlation_id):
        raise OutcomeMismatch("correlation_id mismatch")

    with transaction.atomic():
        locked = OperationCommand.objects.select_for_update().get(pk=command.pk)
        # the outcome must descend from this command's own request event, so a misrouted or forged outcome cannot finalise it
        if str(causation_id) != str(locked.request_event_id):
            raise OutcomeMismatch("causation_id does not match command request_event_id")
        _assert_outcome_matches_intent(locked, data, success)
        if locked.status in OperationCommand.TERMINAL:
            return locked  # terminal is final; a redelivered outcome is a no-op
        if success:
            locked.status = OperationCommand.Status.SUCCEEDED
            locked.result_code = ""
            locked.result_detail = ""
        else:
            locked.status = OperationCommand.Status.REJECTED
            locked.result_code = str(data.reject_code)
            locked.result_detail = data.detail
        locked.save(update_fields=["status", "result_code", "result_detail", "updated_at"])
        return locked


class ClaimResult(StrEnum):
    CLAIMED = "claimed"          # leased by this worker, safe to publish
    BUSY = "busy"                # another worker holds an unexpired lease
    EXPIRED = "expired"          # past deadline and never sent, finalised locally
    UNAVAILABLE = "unavailable"  # already published, suppressed, or command finished


def _suppress_expired(row: OperationsOutbox, command: OperationCommand) -> None:
    row.status = OperationsOutbox.Status.SUPPRESSED
    row.save(update_fields=["status"])
    command.status = OperationCommand.Status.REJECTED
    command.result_code = str(TransitionRejectCode.command_expired)
    command.result_detail = "expired before any publish attempt"
    command.save(update_fields=["status", "result_code", "result_detail", "updated_at"])
    OperationAuditLog.objects.create(
        actor_id=str(command.actor_id), actor_role=ACTOR_ROLE, action=command.command_type,
        target=command.target, command_id=command.command_id, result="command_expired",
    )


def claim_or_expire(row_id: int, *, worker: str, lease: timedelta):
    """leases one row for publishing, or finalises it when it expired before ever being sent

    Locks outbox before command, the same order expire_before_dispatch uses. The attempt stamp
    and the fencing token are written here, so a row handed to the network cannot be suppressed
    and a superseded worker cannot complete it later.
    """
    now = timezone.now()
    with transaction.atomic():
        row = (
            OperationsOutbox.objects.select_for_update(skip_locked=True)
            .filter(pk=row_id, status=OperationsOutbox.Status.PENDING)
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .first()
        )
        if row is None:
            still_pending = OperationsOutbox.objects.filter(
                pk=row_id, status=OperationsOutbox.Status.PENDING
            ).exists()
            return (ClaimResult.BUSY if still_pending else ClaimResult.UNAVAILABLE), None

        command = None
        if row.command_id is not None:
            command = OperationCommand.objects.select_for_update().get(pk=row.command_id)
            if command.status in OperationCommand.TERMINAL:
                return ClaimResult.UNAVAILABLE, None
            expired = command.deadline_at is not None and command.deadline_at <= now
            if expired and row.publish_attempted_at is None:
                if command.status == OperationCommand.Status.PENDING:
                    _suppress_expired(row, command)
                    return ClaimResult.EXPIRED, None
                return ClaimResult.UNAVAILABLE, None

        if row.publish_attempted_at is None:
            row.publish_attempted_at = now
        row.lease_token = uuid.uuid4()
        row.locked_by = worker
        row.locked_until = now + lease
        row.save(update_fields=["publish_attempted_at", "lease_token", "locked_by", "locked_until"])
        return ClaimResult.CLAIMED, row


def mark_published(row: OperationsOutbox) -> bool:
    """completes the attempt only if this worker still holds the lease it was given"""
    return bool(
        OperationsOutbox.objects.filter(
            pk=row.pk, lease_token=row.lease_token, status=OperationsOutbox.Status.PENDING
        ).update(
            status=OperationsOutbox.Status.PUBLISHED, published_at=timezone.now(),
            attempts=F("attempts") + 1, locked_until=None, locked_by="", lease_token=None,
        )
    )


def schedule_retry(row: OperationsOutbox, *, backoff: timedelta, error: str = "") -> bool:
    """releases the lease for a later attempt, only for the worker that still holds it"""
    return bool(
        OperationsOutbox.objects.filter(pk=row.pk, lease_token=row.lease_token).update(
            attempts=F("attempts") + 1, next_attempt_at=timezone.now() + backoff,
            last_error=error[:1000], locked_until=None, locked_by="", lease_token=None,
        )
    )


def expire_before_dispatch(command: OperationCommand) -> OperationCommand:
    """sweeper entry point for a command that expired before it ever reached the broker"""
    with transaction.atomic():
        row = (
            OperationsOutbox.objects.select_for_update()
            .filter(command_id=command.pk)
            .first()
        )
        locked = OperationCommand.objects.select_for_update().get(pk=command.pk)
        if locked.status != OperationCommand.Status.PENDING:
            return locked
        if row is None or row.publish_attempted_at is not None:
            return locked
        if row.status != OperationsOutbox.Status.PENDING:
            return locked
        _suppress_expired(row, locked)
        return locked


def _advance(command: OperationCommand, to_status, *, allowed) -> OperationCommand:
    with transaction.atomic():
        locked = OperationCommand.objects.select_for_update().get(pk=command.pk)
        if locked.status in allowed:
            locked.status = to_status
            locked.save(update_fields=["status", "updated_at"])
        return locked


def mark_dispatched(command: OperationCommand) -> OperationCommand:
    # a fresh publish, or a successful re-publish after dispatch_failed, confirmed to the broker.
    # timed_out is NOT re-dispatched: its deadline has already elapsed, so it stays a
    # reconciliation signal until an outcome arrives.
    return _advance(
        command, OperationCommand.Status.DISPATCHED,
        allowed={OperationCommand.Status.PENDING, OperationCommand.Status.DISPATCH_FAILED},
    )


def mark_timed_out(command: OperationCommand) -> OperationCommand:
    """
    deadline elapsed with delivery unresolved; NOT terminal, a late outcome may finalise it

    a pending command counts as unresolved only once it actually reached the network. Marking a
    never-sent one timed_out would strand it forever: the claim refuses an expired row and
    expiry only acts on a pending command, so nothing would ever touch it again.
    """
    with transaction.atomic():
        row = OperationsOutbox.objects.select_for_update().filter(command_id=command.pk).first()
        locked = OperationCommand.objects.select_for_update().get(pk=command.pk)
        if locked.status == OperationCommand.Status.PENDING:
            if row is None or row.publish_attempted_at is None:
                return locked
        elif locked.status != OperationCommand.Status.DISPATCHED:
            return locked
        locked.status = OperationCommand.Status.TIMED_OUT
        locked.save(update_fields=["status", "updated_at"])
        return locked


def mark_dispatch_failed(command: OperationCommand) -> OperationCommand:
    # the requested event exhausted its publish retries and was dead-lettered. Under
    # at-least-once delivery this does NOT prove the storefront never received it, so this is a
    # non-terminal alert/reconciliation state: a late outcome may still finalise the command.
    return _advance(
        command, OperationCommand.Status.DISPATCH_FAILED, allowed={OperationCommand.Status.PENDING}
    )
