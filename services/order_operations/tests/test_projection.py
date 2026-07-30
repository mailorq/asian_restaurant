import datetime as dt
import uuid
from decimal import Decimal

import pytest
from event_contracts import EVENT_ORDER_CREATED, EVENT_ORDER_STATUS_CHANGED, parse_event

from operations import projection
from operations.models import CustomerProjection, InboxEvent, OperationOrder

pytestmark = pytest.mark.django_db


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
