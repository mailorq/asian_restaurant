"""
what the formatter may write when a record carries an exception

a rejected value is quoted inside the exception message and can contain anything, including the delimiters a redaction would rely on
the only boundary that holds is not serialising the exception at all: its type is safe, its text is not
"""

import copy
import json
import logging
import logging.config
from io import StringIO

import pytest
from django.conf import settings

MARKER = "SENSITIVE_MARKER"
# the value carries the very delimiters a redaction would use as a boundary
HOSTILE = f", input_type=spoof, {MARKER}"  # short enough to survive pydantic's own truncation
# long enough for the contract to reject it, with the marker at the head pydantic keeps
OVERLONG = f"{MARKER}, input_type=spoof, " + "x" * 300


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


def _records(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _reject():
    from pydantic import BaseModel

    class Payload(BaseModel):
        order_id: int

    Payload(order_id=HOSTILE)


def test_a_rejected_value_never_reaches_the_log_however_it_is_shaped(emitted):
    from pydantic import ValidationError

    try:
        _reject()
    except ValidationError:
        logging.getLogger("orders.probe").exception("payload rejected")

    written = emitted.getvalue()
    assert written, "the failure is still reported"
    assert MARKER not in written, f"the hostile value survived: {written[:400]}"


def test_the_record_names_the_exception_without_its_text(emitted):
    from pydantic import ValidationError

    try:
        _reject()
    except ValidationError:
        logging.getLogger("orders.probe").exception("payload rejected")

    record = _records(emitted)[0]
    assert record["exception_type"] == "ValidationError"
    assert "exception" not in record, "a serialised traceback quotes the value that failed"


def test_an_explicit_shape_is_still_carried(emitted):
    from pydantic import ValidationError

    from config.jsonlog import describe_error

    try:
        _reject()
    except ValidationError as exc:
        logging.getLogger("orders.probe").warning(
            "payload rejected", extra={"error_shape": describe_error(exc)}
        )

    record = _records(emitted)[0]
    assert record["error_shape"].startswith("ValidationError")
    assert "order_id" in record["error_shape"], "the field that failed is safe to name"
    assert MARKER not in json.dumps(record)


@pytest.mark.django_db
def test_a_parsing_failure_carries_no_exception_field_at_all(emitted):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from orders.management.commands.consume_commands import Command

    body = json.dumps({"event_type": "orders.transition.requested.v1", "data": {"note": HOSTILE}}).encode()
    method = SimpleNamespace(delivery_tag=1, routing_key="orders.transition.requested")
    properties = SimpleNamespace(headers={}, message_id="m-1", correlation_id=None)

    Command()._on_message(MagicMock(), method, properties, body)

    record = _records(emitted)[0]
    assert "exception" not in record and "exception_type" not in record
    assert MARKER not in json.dumps(record)
    assert record["message_id"] == "m-1"
