import copy
import json
import logging
import logging.config
from io import StringIO

import pytest
from django.conf import settings

LOGGER = "operations.probe"


@pytest.fixture
def emitted():
    """applies the service logging configuration with the console stream captured"""
    config = copy.deepcopy(settings.LOGGING)
    assert config.get("handlers", {}).get("console"), (
        "no console handler is declared, so operations.* records fall through to "
        "logging.lastResort: WARNING and above, bare format, extra fields dropped"
    )

    stream = StringIO()
    config["handlers"]["console"]["stream"] = stream
    logging.config.dictConfig(config)
    try:
        yield stream
    finally:
        logging.config.dictConfig(settings.LOGGING)


def _records(stream) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_info_from_operations_reaches_a_handler(emitted):
    logging.getLogger(LOGGER).info("projection applied")

    assert _records(emitted), "an INFO record from operations.* was not emitted anywhere"


def test_record_is_one_json_object_per_line(emitted):
    logging.getLogger(LOGGER).warning("command topology not ready")

    records = _records(emitted)
    assert len(records) == 1
    assert records[0]["level"] == "WARNING"
    assert records[0]["logger"] == LOGGER
    assert records[0]["message"] == "command topology not ready"
    assert records[0]["ts"]


def test_extra_fields_survive_formatting(emitted):
    logging.getLogger(LOGGER).warning(
        "outcome does not match its command",
        extra={"correlation_id": "c-1", "command_id": "cmd-1", "trace_id": "t-1"},
    )

    record = _records(emitted)[0]
    assert record["correlation_id"] == "c-1"
    assert record["command_id"] == "cmd-1"
    assert record["trace_id"] == "t-1"


def test_interpolated_message_is_rendered(emitted):
    logging.getLogger(LOGGER).warning("topology not ready: %s", "NOT_FOUND")

    assert _records(emitted)[0]["message"] == "topology not ready: NOT_FOUND"


def test_an_exception_is_named_but_never_quoted(emitted):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger(LOGGER).exception("command publish failed")

    record = _records(emitted)[0]
    assert record["exception_type"] == "ValueError"
    assert "boom" not in json.dumps(record), "an exception message quotes what it was raised over"
    assert record["level"] == "ERROR"


def test_unserialisable_extra_never_breaks_logging(emitted):
    import datetime as dt
    import uuid

    logging.getLogger(LOGGER).warning(
        "envelope violates the contract",
        extra={"event_id": uuid.uuid4(), "occurred_at": dt.datetime.now(dt.UTC)},
    )

    record = _records(emitted)[0]
    assert isinstance(record["event_id"], str) and isinstance(record["occurred_at"], str)


def test_pika_chatter_is_kept_out_of_the_stream(emitted):
    logging.getLogger("pika.adapters.blocking_connection").info("Created channel=1")

    assert _records(emitted) == []


def _nested_log():
    """stands in for a log emitted deeper in the stack, far from the message boundary"""
    logging.getLogger("operations.deep").warning("projection conflict")


def test_bound_context_reaches_a_record_emitted_deeper_in_the_stack(emitted):
    from operations.jsonlog import log_context

    with log_context(correlation_id="c-1", command_id="cmd-1", trace_id="t-1"):
        _nested_log()

    record = _records(emitted)[0]
    assert record["correlation_id"] == "c-1"
    assert record["command_id"] == "cmd-1"
    assert record["trace_id"] == "t-1"


def test_context_does_not_leak_past_its_block(emitted):
    from operations.jsonlog import log_context

    with log_context(correlation_id="c-1"):
        pass
    _nested_log()

    assert "correlation_id" not in _records(emitted)[0]


def test_an_explicit_field_wins_over_the_bound_context(emitted):
    from operations.jsonlog import log_context

    with log_context(correlation_id="from-context"):
        logging.getLogger(LOGGER).warning("x", extra={"correlation_id": "from-call"})

    assert _records(emitted)[0]["correlation_id"] == "from-call"


def test_absent_identifiers_are_not_written_as_null(emitted):
    from operations.jsonlog import log_context

    with log_context(correlation_id="c-1", causation_id=None):
        _nested_log()

    assert "causation_id" not in _records(emitted)[0]


@pytest.mark.django_db
def test_the_consumer_binds_the_envelope_for_records_made_deeper(emitted):
    import datetime as dt
    import json as _json
    import types
    import uuid as _uuid
    from unittest.mock import MagicMock

    from operations.management.commands.run_operations_consumer import Command

    correlation = str(_uuid.uuid4())
    envelope = {
        "event_id": str(_uuid.uuid4()), "event_type": "orders.transition.succeeded.v1",
        "schema_version": 1, "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront", "aggregate": {"type": "order", "id": "1", "version": 2},
        "correlation_id": correlation, "causation_id": str(_uuid.uuid4()),
        "data": {"command_id": str(_uuid.uuid4()), "order_id": 1,
                 "from_status": "created", "status": "confirmed"},
    }
    method = types.SimpleNamespace(delivery_tag=1, routing_key="orders.transition.succeeded.v1")
    properties = types.SimpleNamespace(headers={}, message_id=str(_uuid.uuid4()), correlation_id=None)

    # no command exists for this outcome, so the dispatcher raises and the consumer logs the refusal
    Command()._on_message(MagicMock(), method, properties, _json.dumps(envelope).encode())

    record = next(r for r in _records(emitted) if "outcome does not match" in r["message"])
    assert record["correlation_id"] == correlation
    assert record["event_type"] == "orders.transition.succeeded.v1"
