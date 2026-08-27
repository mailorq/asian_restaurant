import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from event_contracts.envelope import Envelope

SNAPSHOT_AGGREGATES = frozenset({"product", "customer", "order"})

EVENT_ORDER_CREATED = "orders.order.created.v1"
EVENT_ORDER_STATUS_CHANGED = "orders.order.status_changed.v1"
EVENT_STOCK_CHANGED = "inventory.stock_changed.v1"
EVENT_CUSTOMER_CHANGED = "identity.customer_changed.v1"
EVENT_AUTHZ_CHANGED = "identity.authz_changed.v1"
EVENT_SNAPSHOT_CONTROL = "operations.snapshot.control.v1"

# order-transition command plane (operations issues a command, storefront applies it and
# emits the outcome). These carry a command_id that ties the request to its outcome; the
# concurrency guard is expected_status (checked by the sole writer under lock), not
# aggregate.version, so version is not fenced against the data for these types.
EVENT_ORDER_TRANSITION_REQUESTED = "orders.transition.requested.v1"
EVENT_ORDER_TRANSITION_SUCCEEDED = "orders.transition.succeeded.v1"
EVENT_ORDER_TRANSITION_REJECTED = "orders.transition.rejected.v1"

# width matches the storefront DecimalField(max_digits=10, decimal_places=2); a value the
# contract accepts must fit the DB, otherwise the projection write would fail downstream
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


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


class PaymentMethod(StrEnum):
    cash = "cash"
    card = "card"


class SnapshotPhase(StrEnum):
    started = "started"
    completed = "completed"


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
    payment_method: PaymentMethod
    items: list[OrderItemData] = Field(min_length=1)

    @model_validator(mode="after")
    def _total_matches_items(self) -> "OrderCreatedData":
        if self.total != sum(i.line_total for i in self.items):
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


class AuthzChangedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_id: int = Field(gt=0)
    authz_version: int = Field(ge=1)
    role_active: bool
    user_active: bool


class SnapshotControlData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_id: str = Field(min_length=1)
    phase: SnapshotPhase
    # immutable source boundary: the REPEATABLE READ snapshot time the run was taken at
    as_of: datetime
    # per aggregate_type expected counts, present on the completed control event
    counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts(self) -> "SnapshotControlData":
        if any(v < 0 for v in self.counts.values()):
            raise ValueError("counts must be non-negative")
        if self.phase == SnapshotPhase.completed:
            if set(self.counts) != SNAPSHOT_AGGREGATES:
                raise ValueError("completed counts must have exactly product, customer, order")
        elif self.counts:
            raise ValueError("started must carry empty counts")
        return self


class TransitionRejectCode(StrEnum):
    stale_status = "stale_status"          # order was not at expected_status under lock
    invalid_transition = "invalid_transition"  # target_status not reachable from current
    order_not_found = "order_not_found"


# free-text width matches storefront OrderStatusHistory.note so a reason/detail always fits
NOTE_MAX = 255


class OrderTransitionRequestedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command_id: uuid.UUID
    actor_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    expected_status: OrderStatus
    target_status: OrderStatus
    reason: str = Field(default="", max_length=NOTE_MAX)

    @model_validator(mode="after")
    def _target_differs(self) -> "OrderTransitionRequestedData":
        if self.expected_status == self.target_status:
            raise ValueError("target_status must differ from expected_status")
        return self


class OrderTransitionSucceededData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command_id: uuid.UUID
    order_id: int = Field(gt=0)
    from_status: OrderStatus
    status: OrderStatus

    @model_validator(mode="after")
    def _status_advances(self) -> "OrderTransitionSucceededData":
        if self.from_status == self.status:
            raise ValueError("succeeded status must differ from from_status")
        return self


class OrderTransitionRejectedData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command_id: uuid.UUID
    order_id: int = Field(gt=0)
    reject_code: TransitionRejectCode
    # order_not_found carries no status; every other reject code is found under lock
    current_status: OrderStatus | None = None
    detail: str = Field(default="", max_length=NOTE_MAX)

    @model_validator(mode="after")
    def _current_status_matches_code(self) -> "OrderTransitionRejectedData":
        not_found = self.reject_code == TransitionRejectCode.order_not_found
        if not_found and self.current_status is not None:
            raise ValueError("order_not_found must not carry current_status")
        if not not_found and self.current_status is None:
            raise ValueError(f"{self.reject_code} requires current_status")
        return self


_REGISTRY: dict[str, type[BaseModel]] = {
    EVENT_ORDER_CREATED: OrderCreatedData,
    EVENT_ORDER_STATUS_CHANGED: OrderStatusChangedData,
    EVENT_STOCK_CHANGED: StockChangedData,
    EVENT_CUSTOMER_CHANGED: CustomerChangedData,
    EVENT_AUTHZ_CHANGED: AuthzChangedData,
    EVENT_SNAPSHOT_CONTROL: SnapshotControlData,
    EVENT_ORDER_TRANSITION_REQUESTED: OrderTransitionRequestedData,
    EVENT_ORDER_TRANSITION_SUCCEEDED: OrderTransitionSucceededData,
    EVENT_ORDER_TRANSITION_REJECTED: OrderTransitionRejectedData,
}

_AGGREGATE: dict[str, tuple[str, str]] = {
    EVENT_ORDER_CREATED: ("order", "order_id"),
    EVENT_ORDER_STATUS_CHANGED: ("order", "order_id"),
    EVENT_STOCK_CHANGED: ("product", "product_code"),
    EVENT_CUSTOMER_CHANGED: ("customer", "customer_id"),
    EVENT_AUTHZ_CHANGED: ("authz", "subject_id"),
    EVENT_SNAPSHOT_CONTROL: ("snapshot", "run_id"),
    EVENT_ORDER_TRANSITION_REQUESTED: ("order", "order_id"),
    EVENT_ORDER_TRANSITION_SUCCEEDED: ("order", "order_id"),
    EVENT_ORDER_TRANSITION_REJECTED: ("order", "order_id"),
}

# who is allowed to originate an event: operations issues the request, the storefront (the
# sole writer) issues the outcome. A mislabelled producer is a provenance violation.
_REQUIRED_PRODUCER: dict[str, str] = {
    EVENT_ORDER_TRANSITION_REQUESTED: "operations",
    EVENT_ORDER_TRANSITION_SUCCEEDED: "storefront",
    EVENT_ORDER_TRANSITION_REJECTED: "storefront",
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
    required_producer = _REQUIRED_PRODUCER.get(envelope.event_type)
    if required_producer is not None and envelope.producer != required_producer:
        raise ContractError(
            f"{envelope.event_type} must be produced by {required_producer!r}, got {envelope.producer!r}"
        )
    if envelope.event_type == EVENT_SNAPSHOT_CONTROL:
        if envelope.snapshot_run_id != data.run_id:
            raise ContractError("snapshot_run_id must match control run_id")
    elif envelope.event_type == EVENT_AUTHZ_CHANGED:
        if envelope.aggregate.version != data.authz_version:
            raise ContractError("aggregate.version must equal authz_version")
    elif envelope.snapshot and not envelope.snapshot_run_id:
        raise ContractError("snapshot aggregate event requires snapshot_run_id")
    return envelope, data
