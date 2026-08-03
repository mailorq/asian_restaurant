from operations.models import (
    CustomerProjection,
    InventoryProjection,
    OperationOrder,
    SnapshotExpectation,
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
        # projection saw a newer live event than this snapshot - expected, not a fault
        return None
    diffs = {k: {"expected": expected[k], "actual": actual[k]} for k in expected if expected[k] != actual[k]}
    if diffs:
        return {"aggregate_type": exp.aggregate_type, "aggregate_id": exp.aggregate_id,
                "kind": "field_mismatch", "version": exp.aggregate_version, "diffs": diffs, "explained": False}
    return None


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
        return _compare(exp, o.aggregate_version,
                        {"status": o.status, "total": str(o.total)},
                        {"status": exp.payload.get("status"), "total": exp.payload.get("total")})
    return None


def reconcile() -> dict:
    discrepancies = [d for exp in SnapshotExpectation.objects.all() if (d := _check(exp)) is not None]
    unexplained = [d for d in discrepancies if not d["explained"]]
    return {
        "checked": SnapshotExpectation.objects.count(),
        "discrepancies": discrepancies,
        "unexplained": len(unexplained),
    }
