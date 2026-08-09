from django.db import transaction

from menu.models import Product, StockAdjustment
from orders.models import OrderOutbox

STOCK_EVENT = "inventory.stock_changed"


def _emit(product: Product, *, snapshot: bool = False, run_id: str = "") -> None:
    OrderOutbox.objects.create(
        aggregate_id=product.code,
        aggregate_version=product.version,
        event_type=STOCK_EVENT,
        routing_key=STOCK_EVENT,
        snapshot=snapshot,
        snapshot_run_id=run_id,
        payload={"product_code": product.code, "name": product.name, "stock_quantity": product.stock_quantity},
    )


def record_stock_change(product: Product, new_quantity: int, *, reason: str, staff=None) -> None:
    # single writer of stock: caller must already hold the Product row lock so the
    # stock write, version bump and outbox event commit atomically in one transaction
    old_quantity = product.stock_quantity
    product.stock_quantity = new_quantity
    product.version += 1
    product.save(update_fields=["stock_quantity", "version"])
    StockAdjustment.objects.create(
        product=product, staff=staff, old_quantity=old_quantity, new_quantity=new_quantity, reason=reason
    )
    _emit(product)


@transaction.atomic
def set_stock(product_id: int, new_quantity: int, *, reason: str, staff=None) -> Product | None:
    product = Product.objects.select_for_update().filter(id=product_id).first()
    if product is None:
        return None
    if new_quantity != product.stock_quantity:
        record_stock_change(product, new_quantity, reason=reason, staff=staff)
    return product


def emit_state(product: Product, *, snapshot: bool = False, run_id: str = "") -> None:
    # re-emit current state at the current version: live seeds a projection, snapshot
    # records a reconciliation expectation
    _emit(product, snapshot=snapshot, run_id=run_id)
