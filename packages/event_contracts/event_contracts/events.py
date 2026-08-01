from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from event_contracts.envelope import Envelope

EVENT_ORDER_CREATED = "orders.order.created.v1"
EVENT_ORDER_STATUS_CHANGED = "orders.order.status_changed.v1"
EVENT_STOCK_CHANGED = "inventory.stock_changed.v1"
EVENT_CUSTOMER_CHANGED = "identity.customer_changed.v1"

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class UnknownEventType(ValueError):
    pass


class ContractError(ValueError):
    pass


class OrderStatus(StrEnum):
    created = "created"
    confirmed = "confirmed"
    preparing = "preparing"
    delivering = "delivering"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderItemData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_product_id: int = Field(gt=0)
    product_code: str = Field(min_length=1)
    name: str
    quantity: int = Field(ge=1)
    unit_price: Money
    line_total: Money

    @model_validator(mode="after")
    def _line_total_matches(self) -> "OrderItemData":
        if self.line_total != self.unit_price * self.quantity:
            raise ValueError("line_total must equal unit_price * quantity")
        return self


class OrderCreatedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    status: OrderStatus
    total: Money
    recipient_name: str = ""
    phone: str = ""
    address: str = ""
    address_verified: bool = False
    items: list[OrderItemData] = Field(default_factory=list)

    @model_validator(mode="after")
    def _total_matches_items(self) -> "OrderCreatedData":
        if self.items and self.total != sum(i.line_total for i in self.items):
            raise ValueError("total must equal sum(line_total)")
        return self


class OrderStatusChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int = Field(gt=0)
    status: OrderStatus
    from_status: str = ""


class StockChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    product_code: str = Field(min_length=1)
    name: str = ""
    stock_quantity: int = Field(ge=0)


class CustomerChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_id: int = Field(gt=0)
    name: str = ""
    phone: str = ""


_REGISTRY: dict[str, type[BaseModel]] = {
    EVENT_ORDER_CREATED: OrderCreatedData,
    EVENT_ORDER_STATUS_CHANGED: OrderStatusChangedData,
    EVENT_STOCK_CHANGED: StockChangedData,
    EVENT_CUSTOMER_CHANGED: CustomerChangedData,
}

_AGGREGATE: dict[str, tuple[str, str]] = {
    EVENT_ORDER_CREATED: ("order", "order_id"),
    EVENT_ORDER_STATUS_CHANGED: ("order", "order_id"),
    EVENT_STOCK_CHANGED: ("product", "product_code"),
    EVENT_CUSTOMER_CHANGED: ("customer", "customer_id"),
}


def parse_event(raw: dict) -> tuple[Envelope, BaseModel]:
    envelope = Envelope.model_validate(raw)
    model = _REGISTRY.get(envelope.event_type)
    if model is None:
        raise UnknownEventType(envelope.event_type)
    if envelope.event_type.endswith(".v1") and envelope.schema_version != 1:
        raise ContractError(f"schema_version must be 1 for {envelope.event_type}")

    data = model.model_validate(envelope.data)
    agg_type, id_field = _AGGREGATE[envelope.event_type]
    if envelope.aggregate.type != agg_type:
        raise ContractError(f"aggregate.type {envelope.aggregate.type!r} != {agg_type!r}")
    if envelope.aggregate.id != str(getattr(data, id_field)):
        raise ContractError("aggregate.id does not match event data")
    return envelope, data
