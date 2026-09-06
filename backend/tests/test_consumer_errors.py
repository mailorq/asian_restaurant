"""
which failures are worth another attempt

a lost connection or a deadlock resolves on its own; a constraint or a bad value does not
the consumer retried every DatabaseError alike, closing every pooled connection each time and reaching the DLQ only after five pointless attempts
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.db import DataError, IntegrityError, InterfaceError, OperationalError

from orders.management.commands import consume_commands
from orders.management.commands.consume_commands import Command as Consumer

pytestmark = pytest.mark.django_db


def _delivery():
    import datetime as dt
    import uuid

    envelope = {
        "event_id": str(uuid.uuid4()), "event_type": "orders.transition.requested.v1",
        "schema_version": 1, "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "operations", "aggregate": {"type": "order", "id": "1", "version": 1},
        "correlation_id": str(uuid.uuid4()), "causation_id": None,
        "data": {"command_id": str(uuid.uuid4()), "actor_id": 1, "actor_authz_version": 1,
                 "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).isoformat(),
                 "order_id": 1, "expected_status": "created", "target_status": "confirmed",
                 "reason": ""},
    }
    method = SimpleNamespace(delivery_tag=1, routing_key="orders.transition.requested")
    properties = SimpleNamespace(headers={}, message_id=str(uuid.uuid4()), correlation_id=None)
    return method, properties, json.dumps(envelope).encode()


def _deliver(monkeypatch, exc):
    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(consume_commands, "apply_transition_command", boom)
    channel = MagicMock()
    Consumer()._on_message(channel, *_delivery())
    return channel


@pytest.mark.parametrize("exc", [OperationalError("connection lost"), InterfaceError("closed")])
def test_a_transient_database_failure_is_retried(monkeypatch, exc):
    channel = _deliver(monkeypatch, exc)

    channel.basic_publish.assert_called_once()
    channel.basic_nack.assert_not_called()


@pytest.mark.parametrize("exc", [IntegrityError("duplicate key"), DataError("value too long")])
def test_a_permanent_database_failure_goes_straight_to_the_dlq(monkeypatch, exc):
    channel = _deliver(monkeypatch, exc)

    channel.basic_nack.assert_called_once()
    assert channel.basic_nack.call_args.kwargs.get("requeue", False) is False or \
        channel.basic_nack.call_args[1].get("requeue") is False
    channel.basic_publish.assert_not_called()


def test_a_negative_retry_header_cannot_buy_extra_attempts():
    assert consume_commands._safe_int(-1000) == 0, "a header below zero would bypass the budget"
    assert consume_commands._safe_int(3) == 3
    assert consume_commands._safe_int("nonsense") == 0


def test_the_consumer_holds_one_unacked_message_at_a_time():
    assert consume_commands.PREFETCH == 1, (
        "a synchronous callback handles one message anyway, so a larger prefetch only widens "
        "the set redelivered after a crash"
    )
