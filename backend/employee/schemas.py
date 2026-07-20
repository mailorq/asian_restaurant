from datetime import datetime

from ninja import Field, Schema

from accounts.models import EMPLOYEE_GROUP
from employee.permissions import is_employee
from orders.models import ACTIVE_ORDER_STATUSES
from orders.schemas import OrderOut


class TransitionIn(Schema):
    to_status: str
    note: str = Field(default="", max_length=255)


class InventoryItemOut(Schema):
    id: int
    code: str
    name: str
    category: str
    stock_quantity: int
    is_active: bool


class AdjustIn(Schema):
    new_quantity: int = Field(ge=0)
    reason: str = Field(min_length=2, max_length=255)


class StockAdjustmentOut(Schema):
    old_quantity: int
    new_quantity: int
    reason: str
    staff: str | None
    created_at: datetime

    @staticmethod
    def resolve_staff(obj) -> str | None:
        return obj.staff.username if obj.staff_id else None


class EmployeeUserOut(Schema):
    id: int
    username: str
    name: str
    phone: str | None
    is_employee: bool
    active_orders_count: int
    date_joined: datetime

    @staticmethod
    def resolve_name(obj) -> str:
        return obj.first_name

    @staticmethod
    def resolve_is_employee(obj) -> bool:
        # prefetch friendly (avoids a query per row when groups are prefetched)
        return obj.is_superuser or any(g.name == EMPLOYEE_GROUP for g in obj.groups.all())

    @staticmethod
    def resolve_active_orders_count(obj) -> int:
        value = getattr(obj, "active_orders_count", None)
        if value is not None:
            return value
        return obj.orders.filter(status__in=ACTIVE_ORDER_STATUSES).count()


class PagedUsers(Schema):
    items: list[EmployeeUserOut]
    total: int
    page: int
    page_size: int


class UserDetailOut(Schema):
    id: int
    username: str
    name: str
    phone: str | None
    is_employee: bool
    orders: list[OrderOut]

    @staticmethod
    def resolve_name(obj) -> str:
        return obj.first_name

    @staticmethod
    def resolve_is_employee(obj) -> bool:
        return is_employee(obj)

    @staticmethod
    def resolve_orders(obj):
        return obj.orders.select_related("delivery_address").prefetch_related("items").order_by("-created_at")


class RoleIn(Schema):
    grant: bool
