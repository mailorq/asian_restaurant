import datetime as dt
import uuid
from decimal import Decimal

import pytest
from event_contracts import (
    EVENT_AUTHZ_CHANGED,
    EVENT_CUSTOMER_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_ORDER_STATUS_CHANGED,
    EVENT_STOCK_CHANGED,
    parse_event,
)
from prometheus_client import REGISTRY

from operations import projection
from operations.models import (
    CustomerProjection,
    EmployeeAuthorization,
    InboxEvent,
    InventoryProjection,
    OperationOrder,
)

pytestmark = pytest.mark.django_db


def _metric(event_type: str, outcome: str) -> float:
    return REGISTRY.get_sample_value(
        "operations_projection_events_total", {"event_type": event_type, "outcome": outcome}
    ) or 0.0


def _created(order_id=1, version=1, customer_id=7, status="created", items=None, total="100.00"):
    if items is None:
        items = [{
            "source_product_id": 1,
            "product_code": "dish_1",
            "name": "Рамен",
            "quantity": 2,
            "unit_price": "50.00",
            "line_total": "100.00",
        }]
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_CREATED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "test",
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "order_id": order_id,
            "customer_id": customer_id,
            "status": status,
            "total": total,
            "recipient_name": "Иван",
            "payment_method": "cash",
            "items": items,
        },
    }
    return parse_event(raw)


def _status(order_id=1, version=2, status="confirmed"):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_STATUS_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "test",
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"order_id": order_id, "status": status, "from_status": "created"},
    }
    return parse_event(raw)


def _stock(product_code="dish_1", version=1, stock=10, name="Рамен"):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_STOCK_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "product", "id": product_code, "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"product_code": product_code, "name": name, "stock_quantity": stock},
    }
    return parse_event(raw)


def _customer(customer_id=7, version=1, name="Иван", phone="+380670000000"):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_CUSTOMER_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "customer", "id": str(customer_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"customer_id": customer_id, "name": name, "phone": phone},
    }
    return parse_event(raw)


def test_versioned_created_builds_projection():
    envelope, data = _created(order_id=10, customer_id=3)
    assert projection.apply(envelope, data) is True
    order = OperationOrder.objects.get(source_order_id=10)
    assert order.status == "created" and order.customer_id == 3
    assert order.items.count() == 1
    assert order.recipient_name == "Иван"
    assert CustomerProjection.objects.get(source_customer_id=3).active_orders_count == 1


def test_apply_is_idempotent_by_event_id():
    envelope, data = _created(order_id=11)
    projection.apply(envelope, data)
    assert projection.apply(envelope, data) is False
    assert InboxEvent.objects.filter(event_id=envelope.event_id).count() == 1


def test_status_before_created_raises_out_of_order():
    envelope, data = _status(order_id=999, version=2)
    with pytest.raises(projection.OutOfOrder):
        projection.apply(envelope, data)
    assert not InboxEvent.objects.filter(event_id=envelope.event_id).exists()
    assert not OperationOrder.objects.filter(source_order_id=999).exists()


def test_status_update_advances_projection():
    created_env, created_data = _created(order_id=12)
    projection.apply(created_env, created_data)
    status_env, status_data = _status(order_id=12, version=2, status="confirmed")
    projection.apply(status_env, status_data)
    assert OperationOrder.objects.get(source_order_id=12).status == "confirmed"


def test_late_created_snapshot_does_not_regress_newer_status():
    created_env, created_data = _created(order_id=13, version=1)
    projection.apply(created_env, created_data)
    status_env, status_data = _status(order_id=13, version=2, status="confirmed")
    projection.apply(status_env, status_data)

    stale_env, stale_data = _created(order_id=13, version=1, status="created")
    assert projection.apply(stale_env, stale_data) is True
    order = OperationOrder.objects.get(source_order_id=13)
    assert order.status == "confirmed" and order.aggregate_version == 2


def test_conflicting_status_same_version_is_rejected():
    created_env, created_data = _created(order_id=30, version=1)
    projection.apply(created_env, created_data)
    s1_env, s1_data = _status(order_id=30, version=2, status="confirmed")
    projection.apply(s1_env, s1_data)

    before = _metric(EVENT_ORDER_STATUS_CHANGED, "conflict")
    s2_env, s2_data = _status(order_id=30, version=2, status="preparing")
    with pytest.raises(projection.ProjectionConflict):
        projection.apply(s2_env, s2_data)

    order = OperationOrder.objects.get(source_order_id=30)
    assert order.status == "confirmed" and order.aggregate_version == 2
    assert not InboxEvent.objects.filter(event_id=s2_env.event_id).exists()
    # the conflict metric is owned by the consumer (it routes to DLQ), not by apply()
    assert _metric(EVENT_ORDER_STATUS_CHANGED, "conflict") == before


def test_stale_lower_version_status_is_safe_noop_with_metric():
    created_env, created_data = _created(order_id=31, version=1)
    projection.apply(created_env, created_data)
    advance_env, advance_data = _status(order_id=31, version=3, status="preparing")
    projection.apply(advance_env, advance_data)

    before = _metric(EVENT_ORDER_STATUS_CHANGED, "stale")
    stale_env, stale_data = _status(order_id=31, version=2, status="confirmed")
    assert projection.apply(stale_env, stale_data) is True

    order = OperationOrder.objects.get(source_order_id=31)
    assert order.status == "preparing" and order.aggregate_version == 3
    assert _metric(EVENT_ORDER_STATUS_CHANGED, "stale") == before + 1


def test_money_projected_as_decimal_without_float_rounding():
    items = [{
        "source_product_id": 1,
        "product_code": "dish_1",
        "name": "Гёдза",
        "quantity": 3,
        "unit_price": "19.99",
        "line_total": "59.97",
    }]
    env, data = _created(order_id=14, items=items, total="59.97")
    projection.apply(env, data)
    item = OperationOrder.objects.get(source_order_id=14).items.get()
    assert item.line_total == Decimal("59.97")
    assert item.unit_price * item.quantity == Decimal("59.97")


def test_stock_greater_version_updates_then_stale_is_noop():
    projection.apply(*_stock(product_code="dish_9", version=1, stock=10))
    projection.apply(*_stock(product_code="dish_9", version=2, stock=4))
    assert InventoryProjection.objects.get(product_code="dish_9").stock_quantity == 4

    projection.apply(*_stock(product_code="dish_9", version=1, stock=999))
    row = InventoryProjection.objects.get(product_code="dish_9")
    assert row.stock_quantity == 4 and row.aggregate_version == 2


def test_stock_same_version_different_event_is_conflict():
    projection.apply(*_stock(product_code="dish_8", version=1, stock=10))
    with pytest.raises(projection.ProjectionConflict):
        projection.apply(*_stock(product_code="dish_8", version=1, stock=3))
    assert InventoryProjection.objects.get(product_code="dish_8").stock_quantity == 10


def test_customer_version_fencing_update_and_conflict():
    projection.apply(*_customer(customer_id=77, version=1, name="Иван"))
    projection.apply(*_customer(customer_id=77, version=2, name="Пётр"))
    assert CustomerProjection.objects.get(source_customer_id=77).name == "Пётр"

    with pytest.raises(projection.ProjectionConflict):
        projection.apply(*_customer(customer_id=77, version=2, name="Другой"))
    assert CustomerProjection.objects.get(source_customer_id=77).name == "Пётр"


def _authz(subject_id=7, version=1, role_active=True, user_active=True):
    raw = {
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
    return parse_event(raw)


def test_authz_projection_builds_and_version_fences():
    projection.apply(*_authz(7, 1, role_active=True))
    ea = EmployeeAuthorization.objects.get(subject_id=7)
    assert ea.role_active and ea.authz_version == 1

    projection.apply(*_authz(7, 2, role_active=False))  # revoke advances the version
    ea.refresh_from_db()
    assert ea.authz_version == 2 and ea.role_active is False

    projection.apply(*_authz(7, 1, role_active=True))  # stale re-grant is a no-op
    ea.refresh_from_db()
    assert ea.authz_version == 2 and ea.role_active is False


def test_authz_same_version_same_state_is_idempotent():
    projection.apply(*_authz(7, 1, role_active=True))
    # a re-emitted state event at the same version is an idempotent no-op, not a conflict
    assert projection.apply(*_authz(7, 1, role_active=True)) is True
    assert EmployeeAuthorization.objects.get(subject_id=7).authz_version == 1


def test_authz_same_version_contradiction_is_conflict():
    projection.apply(*_authz(7, 1, role_active=True))
    with pytest.raises(projection.ProjectionConflict):
        projection.apply(*_authz(7, 1, role_active=False))


def test_authz_out_of_order_revoke_then_stale_grant():
    projection.apply(*_authz(7, 1, role_active=True))
    projection.apply(*_authz(7, 2, role_active=False))   # revoke advances
    projection.apply(*_authz(7, 1, role_active=True))     # late grant is stale -> ignored
    ea = EmployeeAuthorization.objects.get(subject_id=7)
    assert ea.authz_version == 2 and ea.role_active is False
