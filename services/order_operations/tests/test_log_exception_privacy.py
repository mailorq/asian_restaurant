"""
what a rejected message may leave in the log, rendered by the real formatter

pydantic puts the value that failed into its message, and for a domain event that value is a customer phone and address
a traceback carries it whole, and the formatter serialises exc_info separately from the message, so redacting the message alone is not enough
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


def _delivery(body: bytes, routing_key: str, event_type: str | None = None):
    method = SimpleNamespace(delivery_tag=1, routing_key=routing_key)
    properties = SimpleNamespace(headers={"occurred_at": "2026-01-01T00:00:00+00:00"},
                                 message_id="m-1", correlation_id=None, type=event_type,
                                 content_type="application/json")
    return MagicMock(), method, properties, body


def test_the_projection_consumer_rejects_a_bad_event_without_quoting_it(emitted):
    from operations.management.commands.run_operations_consumer import Command

    body = json.dumps({
        "event_id": "not-a-uuid", "event_type": "orders.order.created.v1", "schema_version": 1,
        "occurred_at": "2026-01-01T00:00:00+00:00", "producer": "storefront",
        "aggregate": {"type": "order", "id": "1", "version": 1},
        "correlation_id": "11111111-1111-1111-1111-111111111111", "causation_id": None,
        "data": {"order_id": 1, "phone": PHONE, "address": ADDRESS},
    }).encode()

    Command()._on_message(*_delivery(body, "orders.order.created.v1"))

    written = emitted.getvalue()
    assert written, "the rejection still has to be reported"
    assert not _leaked(written), f"the log carries customer data: {written[:400]}"
    assert "m-1" in written, "the operator still needs to find the message"
    assert "exception" not in json.loads(written.splitlines()[0]), _NO_TRACEBACK


def test_the_bridge_rejects_a_bad_event_without_quoting_it(emitted):
    from operations.management.commands.bridge_storefront_events import Command

    body = json.dumps({"order_id": "not-an-int", "phone": PHONE, "address": ADDRESS}).encode()

    Command()._on_message(*_delivery(body, "order.created", event_type="order.created"))

    written = emitted.getvalue()
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
        logging.getLogger("operations.probe").exception("payload rejected")

    written = emitted.getvalue()
    assert "exception" in written, "the traceback is still recorded"
    assert not _leaked(written), "the value that failed must not be in the traceback"
