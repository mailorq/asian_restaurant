import pytest
from django.core.management.base import CommandError
from event_contracts import OrderTransitionSucceededData, parse_event
from pika.exceptions import AMQPConnectionError, ChannelClosedByBroker, UnroutableError

from operations import commands
from operations.commands import create_transition_command
from operations.management.commands import publish_commands
from operations.models import OperationCommand, OperationsOutbox

pytestmark = pytest.mark.django_db

WORKER = "relay-test"


class FakeChannel:
    is_open = True


def _command(order_id=1, key="k1"):
    command, _ = create_transition_command(
        actor_id=42, actor_authz_version=3, order_id=order_id, expected_status="created",
        target_status="confirmed", idempotency_key=key,
    )
    return command


def _relay(monkeypatch, publish):
    relay = publish_commands.Command()
    relay._connection = None
    relay._channel = None
    monkeypatch.setattr(relay, "_open", lambda: FakeChannel())
    monkeypatch.setattr(publish_commands.messaging, "publish_envelope", publish)
    return relay


def _raising(exc):
    def publish(*args, **kwargs):
        raise exc
    return publish


def _recorder():
    sent = []

    def publish(channel, exchange, routing_key, envelope, headers=None):
        sent.append((exchange, routing_key, envelope))
    return sent, publish


def _outbox(command):
    return OperationsOutbox.objects.get(command=command)


def _reload(command):
    return OperationCommand.objects.get(pk=command.pk)


def test_dispatch_writes_the_row_and_the_command_together(monkeypatch):
    command = _command()
    sent, publish = _recorder()

    assert _relay(monkeypatch, publish)._drain(WORKER) == 1

    assert len(sent) == 1
    assert _outbox(command).status == OperationsOutbox.Status.PUBLISHED
    assert _reload(command).status == OperationCommand.Status.DISPATCHED


def test_published_envelope_satisfies_the_contract(monkeypatch):
    command = _command()
    sent, publish = _recorder()

    _relay(monkeypatch, publish)._drain(WORKER)

    exchange, routing_key, envelope = sent[0]
    assert exchange == "commands" and routing_key == "orders.transition.requested"
    parsed, data = parse_event(envelope)
    assert str(parsed.event_id) == str(command.request_event_id)
    assert str(parsed.correlation_id) == str(command.correlation_id)
    assert str(data.command_id) == str(command.command_id)
    assert parsed.producer == "operations"


def test_connection_failure_defers_the_row_and_keeps_the_command_open(monkeypatch):
    command = _command()

    assert _relay(monkeypatch, _raising(AMQPConnectionError("broker down")))._drain(WORKER) == 0

    row = _outbox(command)
    assert row.status == OperationsOutbox.Status.PENDING
    assert row.attempts == 1 and row.next_attempt_at is not None
    assert row.lease_token is None  # the lease is released for the next attempt
    assert _reload(command).status == OperationCommand.Status.PENDING


def test_missing_topology_never_marks_the_command_dispatch_failed(monkeypatch):
    command = _command()
    OperationsOutbox.objects.filter(command=command).update(
        attempts=publish_commands.MAX_ATTEMPTS + 3
    )

    # nothing reached the broker, so this is an operator problem, not delivery uncertainty
    _relay(monkeypatch, _raising(UnroutableError([])))._drain(WORKER)

    assert _reload(command).status == OperationCommand.Status.PENDING
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_broker_closing_the_channel_drops_it_for_the_next_attempt(monkeypatch):
    _command()
    closed = ChannelClosedByBroker(404, "NOT_FOUND - no exchange 'commands'")
    relay = _relay(monkeypatch, _raising(closed))

    relay._drain(WORKER)

    assert relay._channel is None


def test_exhausted_attempts_mark_dispatch_failed(monkeypatch):
    command = _command()
    OperationsOutbox.objects.filter(command=command).update(
        attempts=publish_commands.MAX_ATTEMPTS - 1
    )

    _relay(monkeypatch, _raising(AMQPConnectionError("broker down")))._drain(WORKER)

    assert _reload(command).status == OperationCommand.Status.DISPATCH_FAILED
    # non-terminal: the row stays publishable so a later confirm still advances it
    assert _outbox(command).status == OperationsOutbox.Status.PENDING


def test_expired_command_is_finalised_instead_of_published(monkeypatch):
    command = _command()
    OperationCommand.objects.filter(pk=command.pk).update(
        deadline_at=commands.timezone.now() - commands.COMMAND_TTL
    )
    sent, publish = _recorder()

    assert _relay(monkeypatch, publish)._drain(WORKER) == 0

    assert sent == []
    assert _reload(command).status == OperationCommand.Status.REJECTED
    assert _outbox(command).status == OperationsOutbox.Status.SUPPRESSED


def test_outcome_arriving_before_the_confirm_leaves_the_row_settled(monkeypatch):
    command = _command()

    def publish(channel, exchange, routing_key, envelope, headers=None):
        # the storefront applied the command and its outcome came back before this confirm
        commands.apply_transition_outcome(
            OrderTransitionSucceededData(
                command_id=command.command_id, order_id=int(command.target),
                from_status="created", status="confirmed",
            ),
            correlation_id=command.correlation_id, causation_id=command.request_event_id,
        )

    assert _relay(monkeypatch, publish)._drain(WORKER) == 0

    assert _reload(command).status == OperationCommand.Status.SUCCEEDED
    assert _outbox(command).status == OperationsOutbox.Status.SETTLED


def test_relay_sweeps_expired_commands_on_every_cycle(monkeypatch):
    command = _command()
    result, row = commands.claim_or_expire(
        _outbox(command).pk, worker=WORKER, lease=publish_commands.LEASE
    )
    commands.confirm_dispatch(row)
    OperationCommand.objects.filter(pk=command.pk).update(
        deadline_at=commands.timezone.now() - commands.COMMAND_TTL
    )
    sent, publish = _recorder()

    _relay(monkeypatch, publish)._drain(WORKER)

    assert sent == []  # the row is published; only the command needed attention
    assert _reload(command).status == OperationCommand.Status.TIMED_OUT


def test_relay_refuses_to_start_without_its_own_broker_url(settings):
    settings.COMMANDS_RABBITMQ_URL = ""

    with pytest.raises(CommandError):
        publish_commands.Command().handle(loop=False, interval=1.0)


def test_only_command_events_are_picked_up(monkeypatch):
    _command()
    OperationsOutbox.objects.create(
        routing_key="operations.something", event_type="inventory.stock_changed.v1",
        payload={}, aggregate_id="dish_1",
    )
    sent, publish = _recorder()

    _relay(monkeypatch, publish)._drain(WORKER)

    assert len(sent) == 1 and sent[0][1] == "orders.transition.requested"
