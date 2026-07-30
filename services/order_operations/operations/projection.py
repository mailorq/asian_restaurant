from django.db import transaction
from event_contracts import (
    EVENT_CUSTOMER_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_ORDER_STATUS_CHANGED,
    EVENT_STOCK_CHANGED,
    Envelope,
)

from operations.models import (
    CustomerProjection,
    InboxEvent,
    InventoryProjection,
    OperationOrder,
    OperationOrderItem,
)

ACTIVE_STATUSES = ["created", "confirmed", "preparing", "delivering"]


class OutOfOrder(Exception):
    """A status_changed arrived before its order.created — retry it later."""


@transaction.atomic
def apply(envelope: Envelope, data) -> bool:
    """Idempotently project one versioned event. Returns False if already seen."""
    _, created = InboxEvent.objects.get_or_create(
        event_id=envelope.event_id,
        defaults={"event_type": envelope.event_type, "aggregate_version": envelope.aggregate.version},
    )
    if not created:
        return False

    if envelope.event_type == EVENT_ORDER_CREATED:
        _order_created(envelope, data)
    elif envelope.event_type == EVENT_ORDER_STATUS_CHANGED:
        _order_status_changed(envelope, data)
    elif envelope.event_type == EVENT_STOCK_CHANGED:
        InventoryProjection.objects.update_or_create(
            product_code=data.product_code,
            defaults={"name": data.name, "stock_quantity": data.stock_quantity},
        )
    elif envelope.event_type == EVENT_CUSTOMER_CHANGED:
        CustomerProjection.objects.update_or_create(
            source_customer_id=data.customer_id, defaults={"name": data.name, "phone": data.phone}
        )
    return True


def _order_created(envelope: Envelope, data) -> None:
    existing = OperationOrder.objects.filter(source_order_id=data.order_id).first()
    if existing and existing.aggregate_version > envelope.aggregate.version:
        # replayed/out-of-order snapshot must not regress a newer projection
        return
    order, _ = OperationOrder.objects.update_or_create(
        source_order_id=data.order_id,
        defaults={
            "customer_id": data.customer_id,
            "aggregate_version": envelope.aggregate.version,
            "status": data.status,
            "total": data.total,
            "recipient_name": data.recipient_name,
            "phone": data.phone,
            "address": data.address,
            "address_verified": data.address_verified,
        },
    )
    order.items.all().delete()
    OperationOrderItem.objects.bulk_create(
        OperationOrderItem(
            order=order,
            product_code=item.product_code,
            name=item.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in data.items
    )
    _recount_customer(data.customer_id)


def _order_status_changed(envelope: Envelope, data) -> None:
    order = OperationOrder.objects.filter(source_order_id=data.order_id).first()
    if order is None:
        raise OutOfOrder(f"no projection for order {data.order_id}")
    if envelope.aggregate.version >= order.aggregate_version:
        order.status = data.status
        order.aggregate_version = envelope.aggregate.version
        order.save(update_fields=["status", "aggregate_version", "updated_at"])
        _recount_customer(order.customer_id)


def _recount_customer(customer_id: int) -> None:
    count = OperationOrder.objects.filter(customer_id=customer_id, status__in=ACTIVE_STATUSES).count()
    CustomerProjection.objects.update_or_create(
        source_customer_id=customer_id, defaults={"active_orders_count": count}
    )
