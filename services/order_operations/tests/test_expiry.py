import pytest
from django.utils import timezone

from operations import commands
from operations.commands import create_transition_command
from operations.models import OperationAuditLog, OperationCommand, OperationsOutbox

pytestmark = pytest.mark.django_db


def _command(key="k1"):
    command, _ = create_transition_command(
        actor_id=42, actor_authz_version=3, order_id=1, expected_status="created",
        target_status="confirmed", idempotency_key=key,
    )
    return command


def _outbox(command):
    return OperationsOutbox.objects.get(command=command)


def test_expiry_without_any_publish_attempt_suppresses_the_row():
    command = _command()

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.REJECTED
    assert result.result_code == "command_expired"
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED
    assert OperationAuditLog.objects.filter(command_id=command.command_id, result="command_expired").exists()


def test_expiry_after_a_publish_attempt_leaves_the_command_open():
    command = _command()
    row = _outbox(command)
    commands.mark_publish_attempt(row)

    result = commands.expire_before_dispatch(command)

    # the confirm may have been lost, so the message might already be at the storefront
    assert result.status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_publish_attempt_is_stamped_once():
    command = _command()
    row = _outbox(command)

    commands.mark_publish_attempt(row)
    first = _outbox(command).publish_attempted_at
    commands.mark_publish_attempt(_outbox(command))

    assert first is not None
    assert _outbox(command).publish_attempted_at == first


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


def test_timed_out_command_can_still_be_expired_only_when_never_attempted():
    command = _command()
    commands.mark_timed_out(command)

    result = commands.expire_before_dispatch(command)

    assert result.status == OperationCommand.Status.REJECTED
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED


def test_deadline_is_stored_on_the_command():
    command = _command()
    assert command.deadline_at is not None and command.deadline_at > timezone.now()
