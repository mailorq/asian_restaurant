import datetime as dt
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from event_contracts import (
    EVENT_AUTHZ_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_ORDER_TRANSITION_REJECTED,
    EVENT_ORDER_TRANSITION_REQUESTED,
    EVENT_ORDER_TRANSITION_SUCCEEDED,
    EVENT_SNAPSHOT_CONTROL,
    ContractError,
    Envelope,
    OrderCreatedData,
    OrderTransitionRejectedData,
    OrderTransitionRequestedData,
    OrderTransitionSucceededData,
    UnknownEventType,
    parse_event,
)


def _authz_env(subject_id=5, version=1, role_active=True, user_active=True) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_AUTHZ_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "identity",
        "aggregate": {"type": "authz", "id": str(subject_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"subject_id": subject_id, "authz_version": version,
                 "role_active": role_active, "user_active": user_active},
    }


def _control_env(phase="completed", run_id="r1", envelope_run_id=None, drop_as_of=False, counts=None) -> dict:
    if counts is None:
        counts = {} if phase == "started" else {"product": 1, "customer": 1, "order": 1}
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_SNAPSHOT_CONTROL,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "snapshot_run_id": run_id if envelope_run_id is None else envelope_run_id,
        "aggregate": {"type": "snapshot", "id": run_id, "version": 1},
        "correlation_id": str(uuid.uuid4()),
        "data": {"run_id": run_id, "phase": phase, "as_of": "2026-01-01T00:00:00+00:00", "counts": counts},
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


def test_authz_changed_valid():
    _e, data = parse_event(_authz_env(subject_id=5, version=3, role_active=False))
    assert data.subject_id == 5 and data.authz_version == 3 and data.role_active is False


def test_authz_subject_must_be_positive():
    with pytest.raises(ValidationError):
        parse_event(_authz_env(subject_id=0))


def test_authz_aggregate_version_must_equal_authz_version():
    payload = _authz_env(subject_id=5, version=2)
    payload["data"]["authz_version"] = 3  # contradicts aggregate.version
    with pytest.raises(ContractError):
        parse_event(payload)


def test_control_valid_completed():
    _e, data = parse_event(_control_env(counts={"product": 2, "customer": 1, "order": 3}))
    assert data.phase == "completed" and data.counts["order"] == 3


def test_control_run_id_must_match_envelope():
    with pytest.raises(ContractError):
        parse_event(_control_env(envelope_run_id="other"))


def test_control_as_of_required():
    with pytest.raises(ValidationError):
        parse_event(_control_env(drop_as_of=True))


def test_control_completed_requires_all_three_keys():
    with pytest.raises(ValidationError):
        parse_event(_control_env(counts={"product": 1, "customer": 1}))  # missing order


def test_control_completed_rejects_extra_key():
    with pytest.raises(ValidationError):
        parse_event(_control_env(counts={"product": 1, "customer": 1, "order": 1, "widget": 1}))


def test_control_completed_rejects_negative_count():
    with pytest.raises(ValidationError):
        parse_event(_control_env(counts={"product": -1, "customer": 1, "order": 1}))


def test_control_started_requires_empty_counts():
    parse_event(_control_env(phase="started", counts={}))
    with pytest.raises(ValidationError):
        parse_event(_control_env(phase="started", counts={"product": 1, "customer": 1, "order": 1}))


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


def _transition_env(event_type, data, *, order_id=1, version=1, producer=None) -> dict:
    if producer is None:
        producer = "operations" if event_type == EVENT_ORDER_TRANSITION_REQUESTED else "storefront"
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": producer,
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": data,
    }


def _requested_data(**override) -> dict:
    data = {
        "command_id": str(uuid.uuid4()),
        "actor_id": 42,
        "order_id": 1,
        "expected_status": "created",
        "target_status": "confirmed",
        "reason": "",
    }
    data.update(override)
    return data


def test_transition_requested_valid():
    env, data = parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data()))
    assert isinstance(data, OrderTransitionRequestedData)
    assert data.order_id == 1 and data.expected_status == "created" and data.target_status == "confirmed"


def test_transition_requested_target_must_differ():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_REQUESTED,
            _requested_data(expected_status="confirmed", target_status="confirmed"),
        ))


def test_transition_requested_actor_must_be_positive():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data(actor_id=0)))


def test_transition_requested_bad_command_id_rejected():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data(command_id="nope")))


def test_transition_aggregate_id_must_match_order():
    with pytest.raises(ContractError):
        parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data(order_id=1), order_id=999))


def test_transition_succeeded_valid():
    cid = str(uuid.uuid4())
    env, data = parse_event(_transition_env(
        EVENT_ORDER_TRANSITION_SUCCEEDED,
        {"command_id": cid, "order_id": 1, "from_status": "created", "status": "confirmed"},
    ))
    assert isinstance(data, OrderTransitionSucceededData)
    assert str(data.command_id) == cid and data.status == "confirmed"


def test_transition_rejected_valid_and_code_constrained():
    env, data = parse_event(_transition_env(
        EVENT_ORDER_TRANSITION_REJECTED,
        {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "stale_status",
         "current_status": "preparing", "detail": "already advanced"},
    ))
    assert isinstance(data, OrderTransitionRejectedData)
    assert data.reject_code == "stale_status" and data.current_status == "preparing"


def test_transition_rejected_unknown_code_rejected():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_REJECTED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "banana"},
        ))


def test_transition_rejected_order_not_found_allows_absent_status():
    env, data = parse_event(_transition_env(
        EVENT_ORDER_TRANSITION_REJECTED,
        {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "order_not_found"},
    ))
    assert data.current_status is None


def test_transition_requested_wrong_producer_rejected():
    with pytest.raises(ContractError):
        parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data(), producer="storefront"))


def test_transition_outcome_wrong_producer_rejected():
    with pytest.raises(ContractError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_SUCCEEDED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "from_status": "created", "status": "confirmed"},
            producer="operations",
        ))


def test_transition_succeeded_from_equal_status_rejected():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_SUCCEEDED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "from_status": "confirmed", "status": "confirmed"},
        ))


def test_transition_rejected_stale_requires_current_status():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_REJECTED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "stale_status"},
        ))


def test_transition_rejected_order_not_found_forbids_current_status():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_REJECTED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "order_not_found",
             "current_status": "created"},
        ))


def test_transition_reason_length_capped():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(EVENT_ORDER_TRANSITION_REQUESTED, _requested_data(reason="x" * 256)))


def test_transition_detail_length_capped():
    with pytest.raises(ValidationError):
        parse_event(_transition_env(
            EVENT_ORDER_TRANSITION_REJECTED,
            {"command_id": str(uuid.uuid4()), "order_id": 1, "reject_code": "stale_status",
             "current_status": "created", "detail": "x" * 256},
        ))


def test_total_wider_than_db_field_rejected():
    big = {"source_product_id": 7, "product_code": "dish_1", "name": "X",
           "quantity": 1, "unit_price": "50000000.00", "line_total": "50000000.00"}  # 10 digits, fits
    payload = _envelope()
    payload["data"]["items"] = [dict(big), dict(big)]
    payload["data"]["total"] = "100000000.00"  # 11 digits -> exceeds max_digits=10
    with pytest.raises(ValidationError):
        parse_event(payload)
