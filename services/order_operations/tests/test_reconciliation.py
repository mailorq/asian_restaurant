import datetime as dt
import uuid

import pytest
from event_contracts import (
    EVENT_CUSTOMER_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_ORDER_STATUS_CHANGED,
    EVENT_SNAPSHOT_CONTROL,
    EVENT_STOCK_CHANGED,
    parse_event,
)

from operations import projection
from operations.models import OperationOrder, SnapshotExpectation
from operations.reconciliation import reconcile

pytestmark = pytest.mark.django_db


def _base(event_type, agg_type, agg_id, version, data, snapshot=False, run_id=""):
    return parse_event({
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "storefront",
        "snapshot": snapshot,
        "snapshot_run_id": run_id or None,
        "aggregate": {"type": agg_type, "id": str(agg_id), "version": version},
        "correlation_id": str(uuid.uuid4()),
        "data": data,
    })


def _stock(code="dish_1", version=1, stock=10, snapshot=False, run_id=""):
    return _base(EVENT_STOCK_CHANGED, "product", code, version,
                 {"product_code": code, "name": "Рамен", "stock_quantity": stock}, snapshot, run_id)


def _customer(cid=7, version=1, name="Иван", snapshot=False, run_id=""):
    return _base(EVENT_CUSTOMER_CHANGED, "customer", cid, version,
                 {"customer_id": cid, "name": name, "phone": "+380"}, snapshot, run_id)


def _order(order_id=1, version=1, status="created", total="100.00", address="ул. 1",
           payment_method="cash", items=None, snapshot=False, run_id=""):
    if items is None:
        items = [{"source_product_id": 1, "product_code": "dish_1", "name": "Рамен",
                  "quantity": 2, "unit_price": "50.00", "line_total": "100.00"}]
    return _base(EVENT_ORDER_CREATED, "order", order_id, version,
                 {"order_id": order_id, "customer_id": 5, "status": status, "total": total,
                  "recipient_name": "Иван", "phone": "+380", "address": address, "address_verified": False,
                  "payment_method": payment_method, "items": items}, snapshot, run_id)


def _order_status(order_id=1, version=2, status="confirmed"):
    return _base(EVENT_ORDER_STATUS_CHANGED, "order", order_id, version,
                 {"order_id": order_id, "status": status, "from_status": "created"})


def _control(run_id, phase, counts=None):
    return _base(EVENT_SNAPSHOT_CONTROL, "snapshot", run_id, 1,
                 {"run_id": run_id, "phase": phase, "counts": counts or {}})


def _completed_run(run_id, snapshots, counts):
    projection.apply(*_control(run_id, "started"))
    for pair in snapshots:
        projection.apply(*pair)
    projection.apply(*_control(run_id, "completed", counts))


def test_no_completed_run_is_not_ok():
    assert reconcile()["status"] == "no_completed_run"


def test_healthy_completed_run_is_ok():
    projection.apply(*_stock(code="p1", version=1, stock=10))
    projection.apply(*_customer(cid=5, version=1, name="Иван"))
    projection.apply(*_order(order_id=50, version=1))
    run = "run-healthy"
    _completed_run(run, [
        _stock(code="p1", version=1, stock=10, snapshot=True, run_id=run),
        _customer(cid=5, version=1, name="Иван", snapshot=True, run_id=run),
        _order(order_id=50, version=1, snapshot=True, run_id=run),
    ], {"product": 1, "customer": 1, "order": 1})
    report = reconcile()
    assert report["status"] == "ok" and report["unexplained"] == 0 and report["checked"] == 3


def _order_discrepancy(report):
    return next(d for d in report["discrepancies"] if d["aggregate_type"] == "order")


def test_card_payment_survives_round_trip():
    projection.apply(*_customer(cid=5, version=1))
    projection.apply(*_order(order_id=51, version=1, payment_method="card"))
    assert OperationOrder.objects.get(source_order_id=51).payment_method == "card"
    run = "run-card"
    _completed_run(run, [
        _customer(cid=5, version=1, snapshot=True, run_id=run),
        _order(order_id=51, version=1, payment_method="card", snapshot=True, run_id=run),
    ], {"customer": 1, "order": 1})
    assert reconcile()["status"] == "ok"


def test_lost_payment_method_cannot_reconcile_clean():
    # projection has 'card' but the snapshot lost payment_method -> field_mismatch
    projection.apply(*_customer(cid=5, version=1))
    projection.apply(*_order(order_id=52, version=1, payment_method="card"))
    run = "run-lost-pm"
    _completed_run(run, [
        _customer(cid=5, version=1, snapshot=True, run_id=run),
        _order(order_id=52, version=1, payment_method="cash", snapshot=True, run_id=run),
    ], {"customer": 1, "order": 1})
    report = reconcile()
    assert report["status"] == "discrepancies"
    d = _order_discrepancy(report)
    assert d["kind"] == "field_mismatch" and "payment_method" in d["diffs"]


def test_incomplete_run_manifest_mismatch():
    projection.apply(*_stock(code="p1", version=1, stock=10))
    run = "run-incomplete"
    # completed control claims 2 products, but only one snapshot expectation arrived
    _completed_run(run, [_stock(code="p1", version=1, stock=10, snapshot=True, run_id=run)],
                   {"product": 2})
    assert reconcile()["status"] == "incomplete_run"


def test_deleted_source_aggregate_flagged_as_extra_projection():
    projection.apply(*_stock(code="p1", version=1, stock=10))
    projection.apply(*_stock(code="p2", version=1, stock=5))  # source later removed p2
    run = "run-deleted"
    _completed_run(run, [_stock(code="p1", version=1, stock=10, snapshot=True, run_id=run)],
                   {"product": 1})
    report = reconcile()
    assert report["status"] == "discrepancies" and report["unexplained"] == 1
    d = report["discrepancies"][0]
    assert d["kind"] == "extra_projection" and d["aggregate_id"] == "p2"


def test_missing_source_aggregate_in_operations():
    run = "run-missing"
    _completed_run(run, [_stock(code="p9", version=1, stock=3, snapshot=True, run_id=run)],
                   {"product": 1})
    report = reconcile()
    assert report["unexplained"] == 1 and report["discrepancies"][0]["kind"] == "missing_projection"


def test_order_missed_status_event_is_version_behind():
    projection.apply(*_customer(cid=5, version=1))
    projection.apply(*_order(order_id=60, version=1, status="created"))
    run = "run-missed-status"
    _completed_run(run, [
        _customer(cid=5, version=1, snapshot=True, run_id=run),
        _order(order_id=60, version=2, status="confirmed", snapshot=True, run_id=run),
    ], {"customer": 1, "order": 1})
    assert _order_discrepancy(reconcile())["kind"] == "version_behind"


def test_order_address_and_item_mismatch():
    projection.apply(*_customer(cid=5, version=1))
    projection.apply(*_order(order_id=61, version=1, address="ул. 1"))
    bigger = [{"source_product_id": 1, "product_code": "dish_1", "name": "Рамен",
               "quantity": 3, "unit_price": "50.00", "line_total": "150.00"}]
    run = "run-mismatch"
    _completed_run(run, [
        _customer(cid=5, version=1, snapshot=True, run_id=run),
        _order(order_id=61, version=1, address="ул. 99", total="150.00", items=bigger, snapshot=True, run_id=run),
    ], {"customer": 1, "order": 1})
    d = _order_discrepancy(reconcile())
    assert d["kind"] == "field_mismatch" and {"address", "items", "total"} <= set(d["diffs"])


def test_replay_is_idempotent():
    env, data = _stock(code="p3", version=1, stock=4)
    assert projection.apply(env, data) is True
    assert projection.apply(env, data) is False


def test_repeated_snapshot_upsert_is_idempotent():
    run = "run-repeat"
    projection.apply(*_control(run, "started"))
    for _ in range(3):
        projection.apply(*_stock(code="p4", version=1, stock=8, snapshot=True, run_id=run))
    assert SnapshotExpectation.objects.filter(snapshot_run_id=run, aggregate_id="p4").count() == 1
