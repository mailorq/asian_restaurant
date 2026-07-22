from django.db import transaction

from ops.models import RestaurantOrder
from orders.models import ProcessedEvent

CONSUMER = "ops"


@transaction.atomic
def apply_event(event_id: str, event_type: str, aggregate_version: int, payload: dict) -> bool:
    """
    idempotently project one order event into the ops model

    deduplicates by (event_id, consumer) via the inbox, then upserts the
    RestaurantOrder from the event payload only. returns false when the event
    was already processed. mever touches the storefront Order table
    """
    _, created = ProcessedEvent.objects.get_or_create(event_id=str(event_id), consumer=CONSUMER)
    if not created:
        return False

    source_id = payload["order_id"]

    if event_type == "order.created":
        RestaurantOrder.objects.update_or_create(
            source_order_id=source_id,
            defaults={
                "status": payload.get("status", "created"),
                "total": payload.get("total", "0"),
                "phone": payload.get("phone", ""),
                "items": payload.get("items", []),
                "last_aggregate_version": aggregate_version,
            },
        )
    elif event_type == "order.status_changed":
        projection = RestaurantOrder.objects.filter(source_order_id=source_id).first()
        # only advance the projection; ignore stale / out-of-order updates
        if projection is not None and aggregate_version >= projection.last_aggregate_version:
            projection.status = payload.get("status", projection.status)
            projection.last_aggregate_version = aggregate_version
            projection.save(update_fields=["status", "last_aggregate_version", "updated_at"])

    return True
