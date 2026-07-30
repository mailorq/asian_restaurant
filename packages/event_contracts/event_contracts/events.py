from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from event_contracts.envelope import Envelope

EVENT_ORDER_CREATED = "orders.order.created.v1"
EVENT_ORDER_STATUS_CHANGED = "orders.order.status_changed.v1"
EVENT_STOCK_CHANGED = "inventory.stock_changed.v1"
EVENT_CUSTOMER_CHANGED = "identity.customer_changed.v1"


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
    source_product_id: int
    product_code: str = Field(min_length=1)
    name: str
    quantity: int = Field(ge=1)
    unit_price: Decimal
    line_total: Decimal


class OrderCreatedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int
    customer_id: int
    status: OrderStatus
    total: Decimal
    recipient_name: str = ""
    phone: str = ""
    address: str = ""
    address_verified: bool = False
    items: list[OrderItemData] = Field(default_factory=list)


class OrderStatusChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int
    status: OrderStatus
    from_status: str = ""


class StockChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    product_code: str = Field(min_length=1)
    name: str = ""
    stock_quantity: int = Field(ge=0)


class CustomerChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_id: int
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
