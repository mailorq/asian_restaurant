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


def test_status_change_without_projection_raises_out_of_order():
    with pytest.raises(ops_service.OutOfOrder):
        ops_service.apply_event("evt-orphan", "order.status_changed", 1, {"order_id": 999, "status": "confirmed"})
    # the dedup insert is rolled back, so the event can be retried after created arrives
    assert not ProcessedEvent.objects.filter(event_id="evt-orphan").exists()
    assert not RestaurantOrder.objects.filter(source_order_id=999).exists()


def test_created_projection_includes_delivery_data():
    ops_service.apply_event(
        "evt-addr",
        "order.created",
        1,
        {
            "order_id": 10,
            "status": "created",
            "total": "100",
            "phone": "+380671111111",
            "recipient_name": "Пётр",
            "address": "ул. Садовая, 5",
            "address_verified": True,
            "items": [],
        },
    )
    projection = RestaurantOrder.objects.get(source_order_id=10)
    assert projection.recipient_name == "Пётр"
    assert projection.address == "ул. Садовая, 5"
    assert projection.address_verified is True
