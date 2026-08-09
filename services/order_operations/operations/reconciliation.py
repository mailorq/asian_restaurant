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


def _canonical_items(rows) -> list:
    return sorted([list(r) for r in rows])


def reconcile() -> dict:
    discrepancies = [d for exp in SnapshotExpectation.objects.all() if (d := _check(exp)) is not None]
    unexplained = [d for d in discrepancies if not d["explained"]]
    return {
        "checked": SnapshotExpectation.objects.count(),
        "discrepancies": discrepancies,
        "unexplained": len(unexplained),
    }
