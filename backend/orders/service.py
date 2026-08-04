from decimal import Decimal

from django.db import IntegrityError, transaction

from cart import service as cart_service
from menu import inventory
from menu.models import Product
from orders import geocode as geo
from orders.models import (
    DeliveryAddress,
    Order,
    OrderItem,
    OrderOutbox,
    OrderStatusHistory,
)


class CheckoutError(Exception):
    def __init__(self, code: str, message: str, items: list | None = None) -> None:
        self.code = code
        self.message = message
        self.items = items or []
        super().__init__(message)


def _order_payload(order: Order, items: list[OrderItem]) -> dict:
    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "total": str(order.total),
        "phone": order.phone,
        "recipient_name": order.contact_name,
        "address": order.delivery_address.address,
        "address_verified": order.delivery_address.is_verified,
        "payment_method": order.payment_method,
        "items": [
            {
                "product_id": i.product_id,
                "product_code": i.product.code,
                "name": i.product_name,
                "quantity": i.quantity,
                "unit_price": str(i.unit_price),
                "line_total": str(i.line_total),
            }
            for i in items
        ],
        "created_at": order.created_at.isoformat(),
    }


def _geocode_safe(raw_address: str) -> geo.GeocodeResult:
    try:
        return geo.geocode(raw_address)
    except geo.GeocoderUnavailable:
        return geo.GeocodeResult(found=False)


@transaction.atomic
def _create_order(
    user, cart_items, cart_version, raw_address, geo_result, payment_method, idempotency_key, recipient_name
):
    source_cart_id = f"u:{user.id}"
    locked = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=list(cart_items.keys()))
    }

    problems = []
    for product_id, quantity in cart_items.items():
        product = locked.get(product_id)
        if product is None or not product.is_active:
            problems.append({"product_id": product_id, "name": product.name if product else "", "reason": "unavailable"})
        elif product.stock_quantity < quantity:
            problems.append(
                {"product_id": product_id, "name": product.name, "reason": "insufficient_stock", "available": product.stock_quantity}
            )
    if problems:
        raise CheckoutError("cart_changed", "Корзина изменилась — проверьте наличие товаров", problems)

    address = DeliveryAddress.objects.create(
        user=user,
        address=raw_address.strip()[:500],
        lat=geo_result.lat,
        lng=geo_result.lng,
        is_verified=geo_result.found,
        provider="nominatim" if geo_result.found else "",
    )

    order = Order.objects.create(
        user=user,
        status=Order.Status.CREATED,
        payment_method=payment_method,
        phone=user.phone or "",  # from request.user
        contact_name=(recipient_name or "").strip() or user.first_name or "",
        delivery_address=address,
        total=Decimal("0.00"),
        idempotency_key=idempotency_key,
        source_cart_id=source_cart_id,
        source_cart_version=cart_version,
    )

    total = Decimal("0.00")
    items: list[OrderItem] = []
    for product_id, quantity in cart_items.items():
        product = locked[product_id]
        unit_price = product.price  # server price is authoritative at checkout
        line_total = unit_price * quantity
        total += line_total
        items.append(
            OrderItem(
                order=order,
                product=product,
                product_name=product.name,
                unit_price=unit_price,
                quantity=quantity,
                line_total=line_total,
            )
        )
        inventory.record_stock_change(
            product, product.stock_quantity - quantity, reason=f"order #{order.id}"
        )

    OrderItem.objects.bulk_create(items)
    order.total = total
    order.save(update_fields=["total"])

    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=Order.Status.CREATED, changed_by=user, note="checkout"
    )
    OrderOutbox.objects.create(
        aggregate_id=str(order.id),
        aggregate_version=1,
        event_type="order.created",
        routing_key="order.created",
        payload=_order_payload(order, items),
    )
    return order


def checkout(user, raw_address: str, payment_method: str, idempotency_key: str, recipient_name: str = "") -> Order:
    source_cart_id = f"u:{user.id}"

    existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    key = cart_service.user_key(user.id)
    cart_items, cart_version = cart_service.read_sync(key)
    if not cart_items:
        raise CheckoutError("empty_cart", "Корзина пуста")

    existing = Order.objects.filter(source_cart_id=source_cart_id, source_cart_version=cart_version).first()
    if existing is not None:
        return existing

    geo_result = _geocode_safe(raw_address)  # external http, kept out of the transaction

    try:
        order = _create_order(
            user, cart_items, cart_version, raw_address, geo_result, payment_method, idempotency_key, recipient_name
        )
    except IntegrityError:
        # a concurrent submit won the unique(idempotency_key) / (source_cart_id, version) race
        existing = (
            Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
            or Order.objects.filter(source_cart_id=source_cart_id, source_cart_version=cart_version).first()
        )
        if existing is not None:
            return existing
        raise

    # CAS clear: only wipe the cart if it is still at the version we checked out,
    # so an item added mid-checkout is not silently lost.
    cart_service.clear_sync(key, cart_version)
    return order


@transaction.atomic
def transition(order: Order, new_status: str, changed_by=None, note: str = "", expected_status: str | None = None) -> Order:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if expected_status is not None and locked.status != expected_status:
        raise CheckoutError("stale_order", f"Заказ уже в статусе «{locked.get_status_display()}»")
    if not locked.can_transition_to(new_status):
        raise CheckoutError("invalid_transition", f"Недопустимый переход {locked.status} → {new_status}")

    previous = locked.status
    locked.status = new_status
    locked.save(update_fields=["status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=locked, from_status=previous, to_status=new_status, changed_by=changed_by, note=note
    )
    OrderOutbox.objects.create(
        aggregate_id=str(locked.id),
        aggregate_version=OrderStatusHistory.objects.filter(order=locked).count(),
        event_type="order.status_changed",
        routing_key="order.status_changed",
        payload={"order_id": locked.id, "status": new_status, "from_status": previous},
    )
    return locked


def emit_order_state(order: Order, *, snapshot: bool = False) -> None:
    # order aggregate version is the length of its status history
    items = list(order.items.select_related("product").all())
    OrderOutbox.objects.create(
        aggregate_id=str(order.id),
        aggregate_version=OrderStatusHistory.objects.filter(order=order).count(),
        event_type="order.created",
        routing_key="order.created",
        snapshot=snapshot,
        payload=_order_payload(order, items),
    )
