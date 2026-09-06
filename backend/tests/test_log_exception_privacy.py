"""
what a rejected message may leave in the log, rendered by the real formatter

pydantic puts the value that failed into its message, and for an order event that value is a customer phone and address
the formatter serialises exc_info separately from the message, so redacting the message alone is not enough
"""

import copy
import json
import logging
import logging.config
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db

PHONE = "+380991234567"
ADDRESS = "Kyiv, Secret Street 1, kv 5"


@pytest.fixture
def emitted():
    config = copy.deepcopy(settings.LOGGING)
    stream = StringIO()
    config["handlers"]["console"]["stream"] = stream
    logging.config.dictConfig(config)
    try:
        yield stream
    finally:
        logging.config.dictConfig(settings.LOGGING)


_NO_TRACEBACK = ("a body-parsing failure must not attach a traceback at all: the redaction in the "
                 "formatter is insurance, not the mechanism")


def _leaked(text: str) -> bool:
    return PHONE in text or ADDRESS in text


def test_the_command_consumer_rejects_a_bad_command_without_quoting_it(emitted):
    from orders.management.commands.consume_commands import Command

    body = json.dumps({
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "orders.transition.requested.v1", "schema_version": 1,
        "occurred_at": "2026-01-01T00:00:00+00:00", "producer": "operations",
        "aggregate": {"type": "order", "id": "1", "version": 1},
        "correlation_id": "22222222-2222-2222-2222-222222222222", "causation_id": None,
        "data": {"command_id": "33333333-3333-3333-3333-333333333333", "actor_id": 1,
                 "actor_authz_version": 1, "expires_at": "2030-01-01T00:00:00+00:00",
                 "order_id": 1, "expected_status": "created", "target_status": "confirmed",
                 "reason": f"{ADDRESS}, {PHONE} " * 20},
    }).encode()
    method = SimpleNamespace(delivery_tag=1, routing_key="orders.transition.requested")
    properties = SimpleNamespace(headers={}, message_id="m-1", correlation_id=None)

    Command()._on_message(MagicMock(), method, properties, body)

    written = emitted.getvalue()
    assert written, "the rejection still has to be reported"
    assert not _leaked(written), f"the log carries what the employee typed: {written[:400]}"
    assert "m-1" in written
    assert "exception" not in json.loads(written.splitlines()[0]), _NO_TRACEBACK


def test_the_legacy_ops_consumer_rejects_a_bad_event_without_quoting_it(emitted, monkeypatch):
    import uuid

    # a valid envelope; the body is what fails, raised the way the legacy service raises it
    from ops.management.commands import run_ops_consumer
    from ops.management.commands.run_ops_consumer import (
        KNOWN_EVENT_TYPES,
        SUPPORTED_SCHEMA,
        Command,
    )

    def rejecting(**kwargs):
        raise KeyError(f"{ADDRESS} {PHONE}")

    monkeypatch.setattr(run_ops_consumer.service, "apply_event", rejecting)
    body = json.dumps({"order_id": 1, "phone": PHONE, "address": ADDRESS}).encode()
    method = SimpleNamespace(delivery_tag=1, routing_key="order.created")
    properties = SimpleNamespace(
        headers={"schema_version": SUPPORTED_SCHEMA, "event_id": str(uuid.uuid4()),
                 "aggregate_version": 1, "correlation_id": str(uuid.uuid4())},
        message_id="m-2", correlation_id=None,
        type=sorted(KNOWN_EVENT_TYPES)[0], content_type="application/json",
    )

    Command()._on_message(MagicMock(), method, properties, body)

    written = emitted.getvalue()
    assert "invalid envelope" not in written, "this must reach the body-parsing branch, not the envelope guard"
    assert written and not _leaked(written), f"the log carries customer data: {written[:400]}"
    assert "exception" not in json.loads(written.splitlines()[0]), _NO_TRACEBACK


def test_the_formatter_never_serialises_a_rejected_value(emitted):
    """insurance: a later log.exception on a validation error must not undo this"""
    from pydantic import BaseModel, ValidationError

    class Payload(BaseModel):
        order_id: int

    try:
        Payload(order_id=f"{ADDRESS} {PHONE}")
    except ValidationError:
        logging.getLogger("orders.probe").exception("payload rejected")

    written = emitted.getvalue()
    assert "exception" in written, "the traceback is still recorded"
    assert not _leaked(written)
