from decimal import Decimal

from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from operations.models import OperationOrder

api = NinjaAPI(title="Order Operations API", version="0.1.0", docs_url="/docs")


class HealthOut(Schema):
    status: str


class OpsOrderOut(Schema):
    source_order_id: int
    status: str
    aggregate_version: int
    total: Decimal
    recipient_name: str
    phone: str
    address: str
    address_verified: bool


@api.get("/health", response=HealthOut, tags=["ops"])
def health(request) -> dict:
    return {"status": "ok"}


@api.get("/orders", response=list[OpsOrderOut], tags=["orders"])
def list_orders(request, status: str | None = None):
    qs = OperationOrder.objects.all().order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return qs


@api.get("/orders/{source_order_id}", response=OpsOrderOut, tags=["orders"])
def get_order(request, source_order_id: int):
    order = OperationOrder.objects.filter(source_order_id=source_order_id).first()
    if order is None:
        raise HttpError(404, "not found")
    return order
