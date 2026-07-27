import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from event_contracts import (
    EVENT_ORDER_CREATED,
    Envelope,
    OrderCreatedData,
    UnknownEventType,
    parse_event,
)


def _envelope(**override) -> dict:
    base = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_CREATED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "order", "id": "1", "version": 1},
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "order_id": 1,
            "customer_id": 5,
            "status": "created",
            "total": "100.00",
            "items": [
                {"product_code": "d1", "name": "Рамен", "quantity": 2, "unit_price": "50.00", "line_total": "100.00"}
            ],
        },
    }
    base.update(override)
    return base


def test_valid_envelope_parses():
    envelope, data = parse_event(_envelope())
    assert envelope.event_type == EVENT_ORDER_CREATED
    assert isinstance(data, OrderCreatedData)
    assert data.order_id == 1 and data.items[0].quantity == 2


def test_naive_occurred_at_rejected():
    with pytest.raises(ValidationError):
        Envelope.model_validate(_envelope(occurred_at="2026-01-01T00:00:00"))


def test_aggregate_version_must_be_ge_1():
    with pytest.raises(ValidationError):
        Envelope.model_validate(_envelope(aggregate={"type": "order", "id": "1", "version": 0}))


def test_bad_event_id_rejected():
    with pytest.raises(ValidationError):
        Envelope.model_validate(_envelope(event_id="not-a-uuid"))


def test_unknown_event_type_raises():
    with pytest.raises(UnknownEventType):
        parse_event(_envelope(event_type="orders.unknown.v1"))


def test_missing_required_data_field_rejected():
    payload = _envelope()
    del payload["data"]["customer_id"]
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_backward_compatible_additions_are_ignored():
    payload = _envelope()
    payload["future_top_level"] = "x"
    payload["data"]["loyalty_tier"] = "gold"
    _envelope_obj, data = parse_event(payload)
    assert not hasattr(data, "loyalty_tier")
