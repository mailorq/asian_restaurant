import pytest

from ops import service as ops_service
from ops.models import RestaurantOrder
from orders.models import ProcessedEvent

pytestmark = pytest.mark.django_db


def _payload(order_id=1, status="created", total="200.00"):
    return {
        "order_id": order_id,
        "status": status,
        "total": total,
        "phone": "+380671111111",
        "items": [{"product_id": 1, "name": "Рамен", "quantity": 2, "unit_price": "100.00"}],
    }


def test_apply_created_builds_projection():
    applied = ops_service.apply_event("evt-1", "order.created", 1, _payload(order_id=5))
    assert applied is True
    projection = RestaurantOrder.objects.get(source_order_id=5)
    assert projection.status == "created"
    assert projection.last_aggregate_version == 1


def test_apply_is_idempotent_by_event_id():
    ops_service.apply_event("evt-dup", "order.created", 1, _payload(order_id=6))
    # redelivery of the same event_id is skipped
    applied = ops_service.apply_event("evt-dup", "order.created", 1, _payload(order_id=6, status="confirmed"))
    assert applied is False
    assert RestaurantOrder.objects.get(source_order_id=6).status == "created"  # unchanged
    assert ProcessedEvent.objects.filter(event_id="evt-dup", consumer="ops").count() == 1


def test_status_changed_advances_projection():
    ops_service.apply_event("evt-c", "order.created", 1, _payload(order_id=7))
    ops_service.apply_event("evt-s", "order.status_changed", 2, {"order_id": 7, "status": "confirmed"})
    assert RestaurantOrder.objects.get(source_order_id=7).status == "confirmed"


def test_stale_status_change_is_ignored():
    ops_service.apply_event("evt-c2", "order.created", 3, _payload(order_id=8))
    ops_service.apply_event("evt-old", "order.status_changed", 2, {"order_id": 8, "status": "cancelled"})
    assert RestaurantOrder.objects.get(source_order_id=8).status == "created"  # stale, not applied


def test_status_change_without_projection_is_noop():
    applied = ops_service.apply_event("evt-orphan", "order.status_changed", 1, {"order_id": 999, "status": "confirmed"})
    assert applied is True  # event recorded for dedup, but no projection to update
    assert not RestaurantOrder.objects.filter(source_order_id=999).exists()
