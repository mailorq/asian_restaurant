from django.db import transaction

from ops.models import RestaurantOrder
from orders.models import ProcessedEvent

CONSUMER = "ops"


class OutOfOrder(Exception):
    """A status_changed arrived before its order.created — retry it later."""


@transaction.atomic
def apply_event(event_id: str, event_type: str, aggregate_version: int, payload: dict) -> bool:
    """Idempotently project one order event into the ops model.

    Deduplicates by (event_id, consumer) via the inbox, then upserts the
    RestaurantOrder from the event payload only. Returns False when the event was
    already processed. Never touches the storefront Order table. Raises OutOfOrder
    when a status_changed has no projection yet, so the caller can retry it.
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
                "recipient_name": payload.get("recipient_name", ""),
                "address": payload.get("address", ""),
                "address_verified": payload.get("address_verified", False),
                "items": payload.get("items", []),
                "last_aggregate_version": aggregate_version,
            },
        )
    elif event_type == "order.status_changed":
        projection = RestaurantOrder.objects.filter(source_order_id=source_id).first()
        if projection is None:
            # created not projected yet: roll back the dedup insert and retry later
            raise OutOfOrder(f"no projection for order {source_id}")
        # only advance; ignore a stale (older aggregate_version) update
        if aggregate_version >= projection.last_aggregate_version:
            projection.status = payload.get("status", projection.status)
            projection.last_aggregate_version = aggregate_version
            projection.save(update_fields=["status", "last_aggregate_version", "updated_at"])

    return True
