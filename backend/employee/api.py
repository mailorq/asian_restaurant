from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth

from employee import service
from employee.permissions import employee_required, superuser_required
from employee.schemas import (
    AdjustIn,
    EmployeeUserOut,
    InventoryItemOut,
    PagedUsers,
    RoleIn,
    StockAdjustmentOut,
    TransitionIn,
    UserDetailOut,
)
from menu.models import Product, StockAdjustment
from orders import service as order_service
from orders.models import ACTIVE_ORDER_STATUSES, Order
from orders.schemas import OrderOut

router = Router(tags=["employee"], auth=django_auth)


def _orders_qs():
    return Order.objects.select_related("delivery_address").prefetch_related("items")


# --- orders ---------------------------------------------------------------
@router.get("/orders", response=list[OrderOut])
@employee_required
def list_orders(request, status: str | None = None):
    qs = _orders_qs().order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs


@router.get("/orders/{order_id}", response=OrderOut)
@employee_required
def order_detail(request, order_id: int):
    order = _orders_qs().filter(id=order_id).first()
    if order is None:
        raise HttpError(404, "Заказ не найден")
    return order


@router.post("/orders/{order_id}/transition", response=OrderOut)
@employee_required
def transition_order(request, order_id: int, data: TransitionIn):
    order = Order.objects.filter(id=order_id).first()
    if order is None:
        raise HttpError(404, "Заказ не найден")
    try:
        order_service.transition(order, data.to_status, changed_by=request.auth, note=data.note)
    except order_service.CheckoutError as exc:
        raise HttpError(400, exc.message) from exc
    return _orders_qs().get(pk=order.pk)


# --- inventory ------------------------------------------------------------
@router.get("/inventory", response=list[InventoryItemOut])
@employee_required
def inventory(request, search: str | None = None):
    qs = Product.objects.all().order_by("category", "name")
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
    return qs


@router.post("/inventory/{product_id}/adjust", response=InventoryItemOut)
@employee_required
def adjust_stock(request, product_id: int, data: AdjustIn):
    with transaction.atomic():
        product = Product.objects.select_for_update().filter(id=product_id).first()
        if product is None:
            raise HttpError(404, "Товар не найден")
        old_quantity = product.stock_quantity
        if data.new_quantity != old_quantity:
            product.stock_quantity = data.new_quantity
            product.save(update_fields=["stock_quantity"])
            StockAdjustment.objects.create(
                product=product,
                staff=request.auth,
                old_quantity=old_quantity,
                new_quantity=data.new_quantity,
                reason=data.reason,
            )
    return product


@router.get("/inventory/{product_id}/adjustments", response=list[StockAdjustmentOut])
@employee_required
def stock_adjustments(request, product_id: int):
    return list(StockAdjustment.objects.filter(product_id=product_id).select_related("staff")[:50])


# --- users ----------------------------------------------------------------
@router.get("/users", response=PagedUsers)
@employee_required
def list_users(request, search: str | None = None, page: int = 1, page_size: int = 20):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    qs = (
        get_user_model()
        .objects.prefetch_related("groups")
        .annotate(
            active_orders_count=Count("orders", filter=Q(orders__status__in=ACTIVE_ORDER_STATUSES))
        )
        .order_by("-date_joined")
    )
    if search:
        qs = qs.filter(
            Q(username__icontains=search) | Q(first_name__icontains=search) | Q(phone__icontains=search)
        )
    total = qs.count()
    start = (page - 1) * page_size
    return {"items": list(qs[start : start + page_size]), "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}", response=UserDetailOut)
@employee_required
def user_detail(request, user_id: int):
    user = get_user_model().objects.filter(id=user_id).first()
    if user is None:
        raise HttpError(404, "Пользователь не найден")
    return user


@router.post("/users/{user_id}/role", response=EmployeeUserOut)
@superuser_required
def set_role(request, user_id: int, data: RoleIn):
    target = get_user_model().objects.filter(id=user_id).first()
    if target is None:
        raise HttpError(404, "Пользователь не найден")
    service.set_employee_role(actor=request.auth, target=target, grant=data.grant)
    return (
        get_user_model()
        .objects.prefetch_related("groups")
        .annotate(
            active_orders_count=Count("orders", filter=Q(orders__status__in=ACTIVE_ORDER_STATUSES))
        )
        .get(pk=target.pk)
    )
