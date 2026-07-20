from ninja import Router, Status
from ninja.errors import HttpError
from ninja.security import django_auth

from common.ratelimit import rate_limit
from orders import geocode as geo
from orders import service
from orders.models import DeliveryAddress, Order
from orders.schemas import (
    AddressVerifyIn,
    AddressVerifyOut,
    CheckoutErrorOut,
    CheckoutIn,
    LastAddressOut,
    OrderOut,
)

router = Router(tags=["orders"], auth=django_auth)

CHECKOUT_LIMIT = dict(scope="checkout", limit=10, window=60)
GEOCODE_LIMIT = dict(scope="geocode", limit=20, window=60)


def _with_relations(queryset):
    return queryset.select_related("delivery_address").prefetch_related("items")


@router.post("/address/verify", response=AddressVerifyOut)
@rate_limit(**GEOCODE_LIMIT)
def verify_address(request, data: AddressVerifyIn):
    try:
        result = geo.geocode(data.address)
    except geo.GeocoderUnavailable as exc:
        raise HttpError(503, "Проверка адреса временно недоступна. Повторите позже.") from exc
    return {
        "verified": result.found,
        "display_name": result.display_name,
        "lat": result.lat,
        "lng": result.lng,
    }


@router.get("/address/last", response=LastAddressOut)
def last_address(request):
    address = (
        DeliveryAddress.objects.filter(user=request.auth).order_by("-created_at").first()
    )
    if address is None:
        return {"address": "", "is_verified": False}
    return {"address": address.address, "is_verified": address.is_verified}


@router.post("/checkout", response={200: OrderOut, 409: CheckoutErrorOut, 422: CheckoutErrorOut})
@rate_limit(**CHECKOUT_LIMIT)
def checkout(request, data: CheckoutIn):
    try:
        order = service.checkout(
            request.auth, data.address, data.payment_method, data.idempotency_key, data.recipient_name
        )
    except service.CheckoutError as exc:
        status = 409 if exc.code == "cart_changed" else 422
        return Status(status, {"code": exc.code, "message": exc.message, "items": exc.items})
    return Status(200, _with_relations(Order.objects).get(pk=order.pk))


@router.get("", response=list[OrderOut])
def list_orders(request):
    return _with_relations(Order.objects.filter(user=request.auth))


@router.get("/{order_id}", response=OrderOut)
def get_order(request, order_id: int):
    order = _with_relations(Order.objects.filter(user=request.auth, id=order_id)).first()
    if order is None:
        raise HttpError(404, "Заказ не найден")
    return order
