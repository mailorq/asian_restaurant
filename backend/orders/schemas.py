from datetime import datetime
from typing import Literal

from ninja import Field, Schema


class CheckoutIn(Schema):
    address: str = Field(min_length=5, max_length=500)
    payment_method: Literal["cash", "card"] = "cash"
    idempotency_key: str = Field(min_length=8, max_length=64)
    # editable per-order recipient; prefilled from the profile but never writes it back
    recipient_name: str = Field(default="", max_length=150)


class AddressVerifyIn(Schema):
    address: str = Field(min_length=3, max_length=500)


class LastAddressOut(Schema):
    address: str = ""
    is_verified: bool = False


class AddressVerifyOut(Schema):
    verified: bool
    display_name: str = ""
    lat: float | None = None
    lng: float | None = None


class OrderItemOut(Schema):
    product_id: int
    name: str
    unit_price: float
    quantity: int
    line_total: float


class OrderOut(Schema):
    id: int
    status: str
    payment_method: str
    total: float
    phone: str
    contact_name: str
    address: str
    address_verified: bool
    items: list[OrderItemOut]
    created_at: datetime

    @staticmethod
    def resolve_total(obj) -> float:
        return float(obj.total)

    @staticmethod
    def resolve_address(obj) -> str:
        return obj.delivery_address.address

    @staticmethod
    def resolve_address_verified(obj) -> bool:
        return obj.delivery_address.is_verified

    @staticmethod
    def resolve_items(obj) -> list[dict]:
        return [
            {
                "product_id": i.product_id,
                "name": i.product_name,
                "unit_price": float(i.unit_price),
                "quantity": i.quantity,
                "line_total": float(i.line_total),
            }
            for i in obj.items.all()
        ]


class CheckoutErrorOut(Schema):
    code: str
    message: str
    items: list[dict] = []
