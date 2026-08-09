from operations.models import (
    CustomerProjection,
    InventoryProjection,
    OperationOrder,
    SnapshotExpectation,
    SnapshotRun,
)


def _missing(exp: SnapshotExpectation) -> dict:
    return {"aggregate_type": exp.aggregate_type, "aggregate_id": exp.aggregate_id,
            "kind": "missing_projection", "expected_version": exp.aggregate_version, "explained": False}


def _compare(exp: SnapshotExpectation, projection_version: int, actual: dict, expected: dict) -> dict | None:
    if projection_version < exp.aggregate_version:
        return {"aggregate_type": exp.aggregate_type, "aggregate_id": exp.aggregate_id,
                "kind": "version_behind", "expected_version": exp.aggregate_version,
                "projection_version": projection_version, "explained": False}
    if projection_version > exp.aggregate_version:
        # projection saw a newer live event than this snapshot, not a fault
        return None
    diffs = {k: {"expected": expected[k], "actual": actual[k]} for k in expected if expected[k] != actual[k]}
    if diffs:
        return {"aggregate_type": exp.aggregate_type, "aggregate_id": exp.aggregate_id,
                "kind": "field_mismatch", "version": exp.aggregate_version, "diffs": diffs, "explained": False}
    return None


def _canonical_items(rows) -> list:
    return sorted([list(r) for r in rows])


def _check(exp: SnapshotExpectation) -> dict | None:
    if exp.aggregate_type == "product":
        p = InventoryProjection.objects.filter(product_code=exp.aggregate_id).first()
        if p is None:
            return _missing(exp)
        return _compare(exp, p.aggregate_version,
                        {"stock_quantity": p.stock_quantity},
                        {"stock_quantity": exp.payload.get("stock_quantity")})
    if exp.aggregate_type == "customer":
        c = CustomerProjection.objects.filter(source_customer_id=int(exp.aggregate_id)).first()
        if c is None:
            return _missing(exp)
        return _compare(exp, c.aggregate_version,
                        {"name": c.name, "phone": c.phone},
                        {"name": exp.payload.get("name"), "phone": exp.payload.get("phone")})
    if exp.aggregate_type == "order":
        o = OperationOrder.objects.filter(source_order_id=int(exp.aggregate_id)).first()
        if o is None:
            return _missing(exp)
        p = exp.payload
        actual = {
            "customer_id": o.customer_id, "status": o.status, "total": str(o.total),
            "recipient_name": o.recipient_name, "phone": o.phone, "address": o.address,
            "address_verified": o.address_verified, "payment_method": o.payment_method,
            "items": _canonical_items([(i.product_code, i.name, i.quantity, str(i.unit_price), str(i.line_total))
                                       for i in o.items.all()]),
        }
        expected = {
            "customer_id": p.get("customer_id"), "status": p.get("status"), "total": p.get("total"),
            "recipient_name": p.get("recipient_name"), "phone": p.get("phone"), "address": p.get("address"),
            "address_verified": p.get("address_verified"), "payment_method": p.get("payment_method"),
            "items": _canonical_items([(i["product_code"], i["name"], i["quantity"], i["unit_price"], i["line_total"])
                                       for i in p.get("items", [])]),
        }
        return _compare(exp, o.aggregate_version, actual, expected)
    return None


def _extra_projections(expected_keys: set) -> list:
    # projections a completed run did not cover are obsolete (source aggregate removed)
    out = []
    for p in InventoryProjection.objects.all():
        if ("product", p.product_code) not in expected_keys:
            out.append({"aggregate_type": "product", "aggregate_id": p.product_code,
                        "kind": "extra_projection", "explained": False})
    for c in CustomerProjection.objects.all():
        if ("customer", str(c.source_customer_id)) not in expected_keys:
            out.append({"aggregate_type": "customer", "aggregate_id": str(c.source_customer_id),
                        "kind": "extra_projection", "explained": False})
    for o in OperationOrder.objects.all():
        if ("order", str(o.source_order_id)) not in expected_keys:
            out.append({"aggregate_type": "order", "aggregate_id": str(o.source_order_id),
                        "kind": "extra_projection", "explained": False})
    return out


def _select_run(run_id: str | None) -> SnapshotRun | None:
    qs = SnapshotRun.objects.filter(status="completed")
    return qs.filter(run_id=run_id).first() if run_id else qs.order_by("-completed_at").first()


def reconcile(run_id: str | None = None) -> dict:
    run = _select_run(run_id)
    if run is None:
        return {"status": "no_completed_run", "run_id": run_id, "checked": 0,
                "discrepancies": [], "unexplained": 0}

    exps = list(SnapshotExpectation.objects.filter(snapshot_run_id=run.run_id))
    received: dict[str, int] = {}
    for e in exps:
        received[e.aggregate_type] = received.get(e.aggregate_type, 0) + 1
    # a completed run whose expectations do not match the manifest lost snapshot events
    manifest_ok = all(received.get(t, 0) == n for t, n in run.expected_counts.items())

    expected_keys = {(e.aggregate_type, e.aggregate_id) for e in exps}
    discrepancies = [d for e in exps if (d := _check(e)) is not None]
    discrepancies += _extra_projections(expected_keys)
    unexplained = [d for d in discrepancies if not d["explained"]]

    if not manifest_ok:
        status = "incomplete_run"
    elif unexplained:
        status = "discrepancies"
    else:
        status = "ok"
    return {
        "status": status, "run_id": run.run_id,
        "expected_counts": run.expected_counts, "received_counts": received,
        "checked": len(exps), "discrepancies": discrepancies, "unexplained": len(unexplained),
    }
