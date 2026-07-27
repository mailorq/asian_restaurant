from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from event_contracts.envelope import Envelope

EVENT_ORDER_CREATED = "orders.order.created.v1"
EVENT_ORDER_STATUS_CHANGED = "orders.order.status_changed.v1"
EVENT_STOCK_CHANGED = "inventory.stock_changed.v1"
EVENT_CUSTOMER_CHANGED = "identity.customer_changed.v1"


class UnknownEventType(ValueError):
    """Raised when an envelope carries an event_type with no registered contract."""


# data models tolerate unknown fields (extra="ignore") so a newer producer adding
# an optional field is backward-compatible; required fields still enforce the contract.
class OrderItemData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    product_code: str
    name: str
    quantity: int = Field(ge=1)
    unit_price: Decimal
    line_total: Decimal


class OrderCreatedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int
    customer_id: int
    status: str
    total: Decimal
    recipient_name: str = ""
    phone: str = ""
    address: str = ""
    address_verified: bool = False
    items: list[OrderItemData] = Field(default_factory=list)


class OrderStatusChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: int
    status: str
    from_status: str = ""


class StockChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    product_code: str
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


def parse_event(raw: dict) -> tuple[Envelope, BaseModel]:
    """Validate the envelope and its typed data. Raises UnknownEventType for an
    unregistered event_type and pydantic.ValidationError for a malformed message."""
    envelope = Envelope.model_validate(raw)
    model = _REGISTRY.get(envelope.event_type)
    if model is None:
        raise UnknownEventType(envelope.event_type)
    return envelope, model.model_validate(envelope.data)
