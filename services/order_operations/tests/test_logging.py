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


def test_exception_is_captured_as_text(emitted):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger(LOGGER).exception("command publish failed")

    record = _records(emitted)[0]
    assert "ValueError: boom" in record["exception"]
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
