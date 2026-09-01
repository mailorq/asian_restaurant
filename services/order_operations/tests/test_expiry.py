from datetime import timedelta

import pytest
from django.utils import timezone

from operations import commands
from operations.commands import create_transition_command
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


def _claim(command):
    return commands.claim_for_publish(_outbox(command).pk, worker="w1", lease=LEASE)


def _expire_deadline(command):
    command.deadline_at = timezone.now() - timedelta(seconds=1)
    command.save(update_fields=["deadline_at"])


def test_expiry_without_any_publish_attempt_suppresses_the_row():
    command = _command()

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.REJECTED
    assert result.result_code == "command_expired"
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED
    assert OperationAuditLog.objects.filter(command_id=command.command_id, result="command_expired").exists()


def test_expiry_after_a_publish_attempt_leaves_the_command_open():
    command = _command()
    assert _claim(command) is not None

    result = commands.expire_before_dispatch(command)

    # the confirm may have been lost, so the message might already be at the storefront
    assert result.status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_timed_out_is_never_downgraded_to_rejected():
    command = _command()
    commands.mark_timed_out(command)

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.TIMED_OUT
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_expiry_does_not_reopen_a_terminal_command():
    command = _command()
    command.status = OperationCommand.Status.SUCCEEDED
    command.save(update_fields=["status"])

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.SUCCEEDED
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_suppressed_row_is_not_suppressed_twice():
    command = _command()
    commands.expire_before_dispatch(command)
    before = OperationAuditLog.objects.filter(command_id=command.command_id).count()

    commands.expire_before_dispatch(command)

    assert OperationAuditLog.objects.filter(command_id=command.command_id).count() == before


def test_claim_stamps_the_attempt_once_and_takes_the_lease():
    command = _command()

    first = _claim(command)
    stamped = first.publish_attempted_at
    second = commands.claim_for_publish(_outbox(command).pk, worker="w2", lease=LEASE)

    assert stamped is not None and first.locked_by == "w1"
    assert second.publish_attempted_at == stamped
    assert second.locked_by == "w2"


def test_suppressed_row_is_never_claimed_again():
    command = _command()
    commands.expire_before_dispatch(command)

    assert _claim(command) is None  # suppression guarantees no network publish


def test_claim_refuses_an_expired_row_that_was_never_attempted():
    command = _command()
    _expire_deadline(command)

    assert _claim(command) is None


def test_claim_allows_an_expired_row_that_was_already_attempted():
    command = _command()
    assert _claim(command) is not None
    _expire_deadline(command)

    # already on the wire: keep publishing so the storefront can resolve it with an outcome
    assert _claim(command) is not None


def test_claim_refuses_a_terminal_command():
    command = _command()
    command.status = OperationCommand.Status.SUCCEEDED
    command.save(update_fields=["status"])

    assert _claim(command) is None
