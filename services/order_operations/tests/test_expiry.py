from datetime import timedelta

import pytest
from django.utils import timezone
from event_contracts import OrderTransitionRejectedData, OrderTransitionSucceededData

from operations import commands
from operations.commands import ClaimResult, create_transition_command
from operations.models import OperationAuditLog, OperationCommand, OperationsOutbox

pytestmark = pytest.mark.django_db

LEASE = timedelta(seconds=60)


def _command(key="k1"):
    command, _ = create_transition_command(
        actor_id=42, actor_authz_version=3, order_id=1, expected_status="created",
        target_status="confirmed", idempotency_key=key,
    )
    return command


def _outbox(command):
    return OperationsOutbox.objects.get(command=command)


def _claim(command, worker="w1", lease=LEASE):
    return commands.claim_or_expire(_outbox(command).pk, worker=worker, lease=lease)


def _expire_deadline(command):
    command.deadline_at = timezone.now() - timedelta(seconds=1)
    OperationCommand.objects.filter(pk=command.pk).update(deadline_at=command.deadline_at)


def _succeeded(command):
    return OrderTransitionSucceededData(
        command_id=command.command_id, order_id=int(command.target),
        from_status="created", status="confirmed",
    )


def _rejected(command):
    return OrderTransitionRejectedData(
        command_id=command.command_id, order_id=int(command.target),
        reject_code="stale_status", current_status="preparing", detail="x",
    )


def _outcome(command, data):
    return commands.apply_transition_outcome(
        data, correlation_id=command.correlation_id, causation_id=command.request_event_id
    )


def _release_lease(command):
    OperationsOutbox.objects.filter(command=command).update(
        locked_until=timezone.now() - timedelta(seconds=1)
    )


# --- expiry ---------------------------------------------------------------
def test_expiry_without_any_publish_attempt_suppresses_the_row():
    command = _command()
    _expire_deadline(command)

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.REJECTED
    assert result.result_code == "command_expired"
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED
    assert OperationAuditLog.objects.filter(command_id=command.command_id, result="command_expired").exists()


def test_expiry_after_a_publish_attempt_leaves_the_command_open():
    command = _command()
    assert _claim(command)[0] is ClaimResult.CLAIMED
    _expire_deadline(command)

    result = commands.expire_before_dispatch(command)

    # the confirm may have been lost, so the message might already be at the storefront
    assert result.status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_timed_out_is_never_downgraded_to_rejected():
    command = _command()
    _claim(command)  # only an attempted command past its deadline can be timed_out
    _expire_deadline(command)
    commands.mark_timed_out(command)

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.TIMED_OUT
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_expiry_does_not_reopen_a_terminal_command():
    command = _command()
    _expire_deadline(command)
    command.status = OperationCommand.Status.SUCCEEDED
    command.save(update_fields=["status"])

    assert commands.expire_before_dispatch(command).status == OperationCommand.Status.SUCCEEDED
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_suppressed_row_is_not_suppressed_twice():
    command = _command()
    _expire_deadline(command)
    commands.expire_before_dispatch(command)
    before = OperationAuditLog.objects.filter(command_id=command.command_id).count()

    commands.expire_before_dispatch(command)

    assert OperationAuditLog.objects.filter(command_id=command.command_id).count() == before


def test_expiry_refuses_a_command_whose_deadline_has_not_passed():
    command = _command()

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING
    assert not OperationAuditLog.objects.filter(result="command_expired").exists()


def test_expiry_refuses_a_command_without_a_deadline():
    command = _command()
    OperationCommand.objects.filter(pk=command.pk).update(deadline_at=None)

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_timeout_refuses_a_command_whose_deadline_has_not_passed():
    command = _command()
    _claim(command)  # on the wire, but its time is not up yet

    assert commands.mark_timed_out(command).status == OperationCommand.Status.PENDING


# --- outcome closes the attempt ------------------------------------------
def test_outcome_settles_a_row_whose_publisher_confirm_was_lost():
    command = _command()
    _, row = _claim(command)  # attempt stamped, then the relay dies before the confirm
    assert row.publish_attempted_at is not None

    assert _outcome(command, _succeeded(command)).status == OperationCommand.Status.SUCCEEDED

    stored = _outbox(command)
    assert stored.status == OperationsOutbox.Status.SETTLED
    assert stored.lease_token is None and stored.locked_until is None and stored.locked_by == ""
    assert _claim(command)[0] is ClaimResult.UNAVAILABLE


def test_rejected_outcome_also_settles_the_row():
    command = _command()
    _claim(command)

    assert _outcome(command, _rejected(command)).status == OperationCommand.Status.REJECTED
    assert _outbox(command).status == OperationsOutbox.Status.SETTLED


def test_published_row_is_left_alone_by_the_outcome():
    command = _command()
    _, row = _claim(command)
    commands.mark_published(row)

    _outcome(command, _succeeded(command))

    assert _outbox(command).status == OperationsOutbox.Status.PUBLISHED


# --- lease ----------------------------------------------------------------
def test_second_worker_is_refused_while_the_lease_holds():
    command = _command()
    assert _claim(command, worker="w1")[0] is ClaimResult.CLAIMED

    result, row = _claim(command, worker="w2")

    assert result is ClaimResult.BUSY and row is None
    assert _outbox(command).locked_by == "w1"


def test_second_worker_takes_over_after_the_lease_expires():
    command = _command()
    _, first = _claim(command, worker="w1")
    _release_lease(command)

    result, second = _claim(command, worker="w2")

    assert result is ClaimResult.CLAIMED
    assert second.locked_by == "w2"
    assert second.lease_token != first.lease_token
    assert second.publish_attempted_at == first.publish_attempted_at  # stamped once


def test_superseded_worker_cannot_mark_published():
    command = _command()
    _, stale = _claim(command, worker="w1")
    _release_lease(command)
    _claim(command, worker="w2")

    assert commands.mark_published(stale) is False
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_superseded_worker_cannot_schedule_retry():
    command = _command()
    _, stale = _claim(command, worker="w1")
    _release_lease(command)
    _, fresh = _claim(command, worker="w2")

    assert commands.schedule_retry(stale, backoff=timedelta(seconds=30)) is False
    assert _outbox(command).lease_token == fresh.lease_token


def test_unclaimed_row_cannot_be_marked_published():
    command = _command()

    # a NULL token is not a lease; without this the IS NULL match would publish an event that
    # was never handed to the broker
    assert commands.mark_published(_outbox(command)) is False
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_unclaimed_row_cannot_schedule_retry():
    command = _command()

    assert commands.schedule_retry(_outbox(command), backoff=timedelta(seconds=30)) is False
    assert _outbox(command).attempts == 0


def test_a_row_without_a_token_is_never_completed():
    command = _command()
    # a live lock window with no token: the two fencing checks only differ here, so this is
    # what pins IS NULL from passing for a lease that was never handed out
    OperationsOutbox.objects.filter(command=command).update(
        locked_until=timezone.now() + LEASE, locked_by="w1"
    )

    row = _outbox(command)
    assert commands.mark_published(row) is False
    assert commands.schedule_retry(row, backoff=timedelta(seconds=30)) is False
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_expired_lease_cannot_be_completed():
    command = _command()
    _, row = _claim(command)
    _release_lease(command)

    assert commands.mark_published(row) is False
    assert commands.schedule_retry(row, backoff=timedelta(seconds=30)) is False
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_lease_holder_completes_and_releases_the_row():
    command = _command()
    _, row = _claim(command)

    assert commands.mark_published(row) is True
    stored = _outbox(command)
    assert stored.status == OperationsOutbox.Status.PUBLISHED
    assert stored.lease_token is None and stored.locked_by == ""


def test_retry_releases_the_lease_and_defers_the_row():
    command = _command()
    _, row = _claim(command)

    assert commands.schedule_retry(row, backoff=timedelta(seconds=30), error="boom") is True
    stored = _outbox(command)
    assert stored.lease_token is None and stored.attempts == 1
    assert _claim(command, worker="w2")[0] is ClaimResult.BUSY  # still inside the backoff window


# --- claim decisions ------------------------------------------------------
def test_suppressed_row_is_never_claimed_again():
    command = _command()
    _expire_deadline(command)
    commands.expire_before_dispatch(command)

    assert _claim(command)[0] is ClaimResult.UNAVAILABLE


def test_claim_expires_a_row_that_was_never_attempted():
    command = _command()
    _expire_deadline(command)

    result, row = _claim(command)

    assert result is ClaimResult.EXPIRED and row is None
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED
    assert OperationCommand.objects.get(pk=command.pk).status == OperationCommand.Status.REJECTED


def test_claim_allows_an_expired_row_that_was_already_attempted():
    command = _command()
    assert _claim(command)[0] is ClaimResult.CLAIMED
    _expire_deadline(command)
    _release_lease(command)

    # already on the wire: keep publishing so the storefront can resolve it with an outcome
    assert _claim(command, worker="w2")[0] is ClaimResult.CLAIMED


def test_claim_refuses_a_terminal_command():
    command = _command()
    command.status = OperationCommand.Status.SUCCEEDED
    command.save(update_fields=["status"])

    assert _claim(command)[0] is ClaimResult.UNAVAILABLE


def test_never_attempted_command_cannot_get_stuck_in_timed_out():
    command = _command()
    _expire_deadline(command)

    # a sweeper that marks a never-sent command timed_out would strand it: claim refuses an
    # expired row and expiry refuses anything that is no longer pending
    commands.mark_timed_out(command)

    assert _claim(command)[0] is ClaimResult.EXPIRED
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED
    assert OperationCommand.objects.get(pk=command.pk).status == OperationCommand.Status.REJECTED
