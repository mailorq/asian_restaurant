import datetime as dt
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from event_contracts import (
    EVENT_ORDER_CREATED,
    EVENT_SNAPSHOT_CONTROL,
    ContractError,
    Envelope,
    OrderCreatedData,
    UnknownEventType,
    parse_event,
)


def _control_env(phase="completed", run_id="r1", envelope_run_id=None, drop_as_of=False, counts=None) -> dict:
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_SNAPSHOT_CONTROL,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "snapshot_run_id": run_id if envelope_run_id is None else envelope_run_id,
        "aggregate": {"type": "snapshot", "id": run_id, "version": 1},
        "correlation_id": str(uuid.uuid4()),
        "data": {"run_id": run_id, "phase": phase, "as_of": "2026-01-01T00:00:00+00:00", "counts": counts or {}},
    }
    if drop_as_of:
        del payload["data"]["as_of"]
    return payload


def _envelope(**override) -> dict:
    base = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_CREATED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "order", "id": "1", "version": 1},
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "order_id": 1,
            "customer_id": 5,
            "status": "created",
            "total": "100.00",
            "payment_method": "cash",
            "items": [
                {
                    "source_product_id": 7,
                    "product_code": "dish_1",
                    "name": "Рамен",
                    "quantity": 2,
                    "unit_price": "50.00",
                    "line_total": "100.00",
                }
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


def test_v1_requires_schema_version_1():
    with pytest.raises(ContractError):
        parse_event(_envelope(schema_version=2))


def test_aggregate_type_mismatch_rejected():
    with pytest.raises(ContractError):
        parse_event(_envelope(aggregate={"type": "product", "id": "1", "version": 1}))


def test_aggregate_id_must_match_event_data():
    with pytest.raises(ContractError):
        parse_event(_envelope(aggregate={"type": "order", "id": "999", "version": 1}))


def test_invalid_status_rejected():
    payload = _envelope()
    payload["data"]["status"] = "teleporting"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_item_requires_product_code():
    payload = _envelope()
    del payload["data"]["items"][0]["product_code"]
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_money_uses_decimal_without_float_rounding():
    payload = _envelope()
    payload["data"]["items"][0].update(unit_price="19.99", quantity=3, line_total="59.97")
    payload["data"]["total"] = "59.97"
    _envelope_obj, data = parse_event(payload)
    assert data.items[0].line_total == Decimal("59.97")
    assert data.items[0].unit_price * data.items[0].quantity == Decimal("59.97")


def test_order_id_must_be_positive():
    payload = _envelope()
    payload["data"]["order_id"] = 0
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_customer_id_must_be_positive():
    payload = _envelope()
    payload["data"]["customer_id"] = 0
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_source_product_id_must_be_positive():
    payload = _envelope()
    payload["data"]["items"][0]["source_product_id"] = 0
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_negative_money_rejected():
    payload = _envelope()
    payload["data"]["items"][0].update(unit_price="-1.00", quantity=1, line_total="-1.00")
    payload["data"]["total"] = "-1.00"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_more_than_two_decimal_places_rejected():
    payload = _envelope()
    payload["data"]["items"][0].update(unit_price="1.999", quantity=1, line_total="1.999")
    payload["data"]["total"] = "1.999"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_line_total_must_equal_unit_price_times_quantity():
    payload = _envelope()
    payload["data"]["items"][0].update(unit_price="50.00", quantity=2, line_total="99.99")
    payload["data"]["total"] = "99.99"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_payment_method_is_required_and_constrained():
    payload = _envelope()
    del payload["data"]["payment_method"]
    with pytest.raises(ValidationError):
        parse_event(payload)
    with pytest.raises(ValidationError):
        parse_event(_envelope(data={**_envelope()["data"], "payment_method": "bitcoin"}))


def test_payment_method_card_accepted():
    payload = _envelope()
    payload["data"]["payment_method"] = "card"
    _e, data = parse_event(payload)
    assert data.payment_method == "card"


def test_control_valid_completed():
    _e, data = parse_event(_control_env(counts={"product": 2, "customer": 1, "order": 3}))
    assert data.phase == "completed" and data.counts["order"] == 3


def test_control_run_id_must_match_envelope():
    with pytest.raises(ContractError):
        parse_event(_control_env(envelope_run_id="other"))


def test_control_as_of_required():
    with pytest.raises(ValidationError):
        parse_event(_control_env(drop_as_of=True))


def test_control_counts_reject_negative_and_unknown_types():
    with pytest.raises(ValidationError):
        parse_event(_control_env(counts={"product": -1}))
    with pytest.raises(ValidationError):
        parse_event(_control_env(counts={"widget": 1}))


def test_snapshot_aggregate_requires_run_id():
    payload = _envelope()
    payload["snapshot"] = True
    payload["snapshot_run_id"] = None
    with pytest.raises(ContractError):
        parse_event(payload)


def test_total_must_equal_sum_of_line_totals():
    payload = _envelope()
    payload["data"]["items"][0].update(unit_price="50.00", quantity=2, line_total="100.00")
    payload["data"]["total"] = "123.45"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_empty_order_with_nonzero_total_rejected():
    payload = _envelope()
    payload["data"]["items"] = []
    payload["data"]["total"] = "100.00"
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_total_wider_than_db_field_rejected():
    big = {"source_product_id": 7, "product_code": "dish_1", "name": "X",
           "quantity": 1, "unit_price": "50000000.00", "line_total": "50000000.00"}  # 10 digits, fits
    payload = _envelope()
    payload["data"]["items"] = [dict(big), dict(big)]
    payload["data"]["total"] = "100000000.00"  # 11 digits -> exceeds max_digits=10
    with pytest.raises(ValidationError):
        parse_event(payload)
