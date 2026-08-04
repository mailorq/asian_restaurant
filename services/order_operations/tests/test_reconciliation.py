import datetime as dt
import uuid

import pytest
from event_contracts import (
    EVENT_ORDER_CREATED,
    EVENT_ORDER_STATUS_CHANGED,
    EVENT_STOCK_CHANGED,
    parse_event,
)

from operations import projection
from operations.models import InventoryProjection, OperationOrder, SnapshotExpectation
from operations.reconciliation import reconcile

pytestmark = pytest.mark.django_db


def _order_created(order_id=1, version=1, status="created", total="100.00", snapshot=False):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_CREATED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "snapshot": snapshot,
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "order_id": order_id, "customer_id": 5, "status": status, "total": total,
            "recipient_name": "Иван", "phone": "+380", "address": "ул. 1", "address_verified": False,
            "items": [{"source_product_id": 1, "product_code": "dish_1", "name": "Рамен",
                       "quantity": 2, "unit_price": "50.00", "line_total": "100.00"}],
        },
    }
    return parse_event(raw)


def _order_status(order_id=1, version=2, status="confirmed"):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_ORDER_STATUS_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "aggregate": {"type": "order", "id": str(order_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"order_id": order_id, "status": status, "from_status": "created"},
    }
    return parse_event(raw)


def _stock(code="dish_1", version=1, stock=10, snapshot=False):
    raw = {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_STOCK_CHANGED,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "snapshot": snapshot,
        "aggregate": {"type": "product", "id": code, "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": {"product_code": code, "name": "Рамен", "stock_quantity": stock},
    }
    return raw, parse_event(raw)


def test_snapshot_records_expectation_without_touching_projection():
    _raw, (env, data) = _stock(code="p1", version=2, stock=7, snapshot=True)
    projection.apply(env, data)
    assert not InventoryProjection.objects.filter(product_code="p1").exists()
    exp = SnapshotExpectation.objects.get(aggregate_type="product", aggregate_id="p1")
    assert exp.aggregate_version == 2 and exp.payload["stock_quantity"] == 7


def test_healthy_has_zero_unexplained():
    _r, (lenv, ldata) = _stock(code="p2", version=1, stock=10)
    projection.apply(lenv, ldata)
    _r, (senv, sdata) = _stock(code="p2", version=1, stock=10, snapshot=True)
    projection.apply(senv, sdata)
    report = reconcile()
    assert report["unexplained"] == 0


def test_replay_is_idempotent_and_reconciles():
    raw, (lenv, ldata) = _stock(code="p3", version=1, stock=4)
    projection.apply(lenv, ldata)
    _env2, data2 = parse_event(raw)  # same event_id delivered again
    assert projection.apply(lenv, data2) is False
    _r, (senv, sdata) = _stock(code="p3", version=1, stock=4, snapshot=True)
    projection.apply(senv, sdata)
    assert reconcile()["unexplained"] == 0


def test_missed_event_is_reported():
    _r, (lenv, ldata) = _stock(code="p4", version=1, stock=10)
    projection.apply(lenv, ldata)
    # a real change happened at v2 but its live event never arrived; only the snapshot did
    _r, (senv, sdata) = _stock(code="p4", version=2, stock=5, snapshot=True)
    projection.apply(senv, sdata)
    report = reconcile()
    assert report["unexplained"] == 1
    assert report["discrepancies"][0]["kind"] == "version_behind"


def test_field_mismatch_at_same_version_is_reported():
    _r, (lenv, ldata) = _stock(code="p5", version=1, stock=10)
    projection.apply(lenv, ldata)
    _r, (senv, sdata) = _stock(code="p5", version=1, stock=999, snapshot=True)
    projection.apply(senv, sdata)
    report = reconcile()
    assert report["unexplained"] == 1
    assert report["discrepancies"][0]["kind"] == "field_mismatch"


def test_repeated_snapshot_is_idempotent_upsert():
    _r, (lenv, ldata) = _stock(code="p6", version=1, stock=8)
    projection.apply(lenv, ldata)
    for _ in range(3):
        _r, (senv, sdata) = _stock(code="p6", version=1, stock=8, snapshot=True)
        projection.apply(senv, sdata)
    assert SnapshotExpectation.objects.filter(aggregate_type="product", aggregate_id="p6").count() == 1
    assert reconcile()["unexplained"] == 0


def test_order_healthy_after_status_change_reconciles():
    projection.apply(*_order_created(order_id=100, version=1, status="created"))
    projection.apply(*_order_status(order_id=100, version=2, status="confirmed"))
    projection.apply(*_order_created(order_id=100, version=2, status="confirmed", snapshot=True))
    assert OperationOrder.objects.get(source_order_id=100).aggregate_version == 2
    assert reconcile()["unexplained"] == 0


def test_order_missed_status_event_is_reported():
    projection.apply(*_order_created(order_id=101, version=1, status="created"))
    # a confirm happened (v2) but its status event was lost; only the snapshot arrived
    projection.apply(*_order_created(order_id=101, version=2, status="confirmed", snapshot=True))
    report = reconcile()
    assert report["unexplained"] == 1
    assert report["discrepancies"][0] == {
        "aggregate_type": "order", "aggregate_id": "101", "kind": "version_behind",
        "expected_version": 2, "projection_version": 1, "explained": False,
    }


def test_order_out_of_order_status_then_reconciles():
    with pytest.raises(projection.OutOfOrder):
        projection.apply(*_order_status(order_id=102, version=2, status="confirmed"))
    projection.apply(*_order_created(order_id=102, version=1, status="created"))
    projection.apply(*_order_status(order_id=102, version=2, status="confirmed"))
    projection.apply(*_order_created(order_id=102, version=2, status="confirmed", snapshot=True))
    assert reconcile()["unexplained"] == 0


def test_order_repeated_snapshot_is_idempotent():
    projection.apply(*_order_created(order_id=103, version=1, status="created"))
    for _ in range(3):
        projection.apply(*_order_created(order_id=103, version=1, status="created", snapshot=True))
    assert SnapshotExpectation.objects.filter(aggregate_type="order", aggregate_id="103").count() == 1
    assert reconcile()["unexplained"] == 0
