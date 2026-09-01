import datetime as dt
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from event_contracts import EVENT_ORDER_STATUS_CHANGED
from prometheus_client import REGISTRY

from operations.management.commands import run_operations_consumer as mod


def _metric(outcome: str) -> float:
    return REGISTRY.get_sample_value(
        "operations_projection_events_total",
        {"event_type": EVENT_ORDER_STATUS_CHANGED, "outcome": outcome},
    ) or 0.0


def _status_body(order_id=5, version=2):
    return json.dumps({
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_STATUS_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"order_id": order_id, "status": "confirmed", "from_status": "created"},
    }).encode()


def _method():
    return SimpleNamespace(delivery_tag=7, routing_key=EVENT_ORDER_STATUS_CHANGED)


def _props(headers=None):
    return SimpleNamespace(headers=headers or {}, message_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()))


def test_conflict_is_routed_to_dlq_with_metric(monkeypatch):
    cmd = mod.Command()
    ch = MagicMock()

    def boom(envelope, data):
        raise mod.projection.ProjectionConflict("order", envelope.aggregate.id, envelope.aggregate.version, envelope.event_id)

    monkeypatch.setattr(mod.dispatch, "handle", boom)
    before = _metric("conflict")

    cmd._on_message(ch, _method(), _props(), _status_body())

    ch.basic_nack.assert_called_once_with(7, requeue=False)
    ch.basic_ack.assert_not_called()
    assert _metric("conflict") == before + 1


def test_out_of_order_is_retried_with_metric(monkeypatch):
    cmd = mod.Command()
    ch = MagicMock()

    def out_of_order(envelope, data):
        raise mod.projection.OutOfOrder("no projection yet")

    monkeypatch.setattr(mod.dispatch, "handle", out_of_order)
    before = _metric("out_of_order")

    cmd._on_message(ch, _method(), _props(), _status_body())

    ch.basic_publish.assert_called_once()
    _, kwargs = ch.basic_publish.call_args
    assert kwargs["exchange"] == mod.messaging.RETRY_EXCHANGE
    ch.basic_ack.assert_called_once_with(7)
    assert _metric("out_of_order") == before + 1


def test_poison_message_goes_to_dlq(monkeypatch):
    cmd = mod.Command()
    ch = MagicMock()
    monkeypatch.setattr(mod.dispatch, "handle", MagicMock())

    cmd._on_message(ch, _method(), _props(), b"{not json")

    ch.basic_nack.assert_called_once_with(7, requeue=False)
    ch.basic_ack.assert_not_called()
