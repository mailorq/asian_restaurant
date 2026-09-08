import logging

from django.db import transaction
from django.utils import timezone
from event_contracts import (
    EVENT_AUTHZ_CHANGED,
    EVENT_CUSTOMER_CHANGED,
    EVENT_ORDER_CREATED,
    EVENT_ORDER_STATUS_CHANGED,
    EVENT_SNAPSHOT_CONTROL,
    EVENT_STOCK_CHANGED,
    Envelope,
)

from operations.metrics import projection_events
from operations.models import (
    CustomerProjection,
    EmployeeAuthorization,
    InboxEvent,
    InventoryProjection,
    OperationOrder,
    OperationOrderItem,
    SnapshotExpectation,
    SnapshotRun,
)

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ["created", "confirmed", "preparing", "delivering"]


class OutOfOrder(Exception):
    """A status_changed arrived before its order.created — retry it later."""


class SnapshotProtocolError(Exception):
    """A snapshot control event violated the started -> completed run protocol."""


class ProjectionConflict(Exception):

    def __init__(self, aggregate: str, aggregate_id, version: int, event_id) -> None:
        self.aggregate = aggregate
        self.aggregate_id = aggregate_id
        self.version = version
        self.event_id = event_id
        super().__init__(f"{aggregate} {aggregate_id}: conflicting event at version {version}")


def remember(envelope: Envelope) -> bool:
    """records the event in the inbox; False means it was already handled"""
    _, created = InboxEvent.objects.get_or_create(
        event_id=envelope.event_id,
        defaults={"event_type": envelope.event_type, "aggregate_version": envelope.aggregate.version},
    )
    if not created:
        projection_events.labels(envelope.event_type, "idempotent").inc()
    return created


@transaction.atomic
def apply(envelope: Envelope, data) -> bool:
    """project one versioned event. returns False if already seen (idempotent)"""
    if not remember(envelope):
        return False
    project(envelope, data)
    return True


def project(envelope: Envelope, data) -> None:
    """applies one event to the projections without touching the inbox"""
    if envelope.event_type == EVENT_SNAPSHOT_CONTROL:
        _handle_control(envelope, data)
        return

    if envelope.snapshot:
        _record_expectation(envelope, data)
        return

    if envelope.event_type == EVENT_ORDER_CREATED:
        _order_created(envelope, data)
    elif envelope.event_type == EVENT_ORDER_STATUS_CHANGED:
        _order_status_changed(envelope, data)
    elif envelope.event_type == EVENT_STOCK_CHANGED:
        _stock_changed(envelope, data)
    elif envelope.event_type == EVENT_CUSTOMER_CHANGED:
        _customer_changed(envelope, data)
    elif envelope.event_type == EVENT_AUTHZ_CHANGED:
        _authz_changed(envelope, data)


def _fence(envelope: Envelope, current_version: int, aggregate: str) -> str:
    incoming = envelope.aggregate.version
    if incoming < current_version:
        log.info(
            "operations projection stale event ignored",
            extra={"event_id": str(envelope.event_id), "event_type": envelope.event_type,
                   "aggregate_id": envelope.aggregate.id, "incoming_version": incoming,
                   "current_version": current_version},
        )
        projection_events.labels(envelope.event_type, "stale").inc()
        return "stale"
    if incoming == current_version:
        raise ProjectionConflict(aggregate, envelope.aggregate.id, incoming, envelope.event_id)
    return "apply"


def _order_created(envelope: Envelope, data) -> None:
    # lock the row so the fencing check and write are atomic against a concurrent writer
    existing = OperationOrder.objects.select_for_update().filter(source_order_id=data.order_id).first()
    if existing and _fence(envelope, existing.aggregate_version, "order") == "stale":
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
            "payment_method": data.payment_method,
            "source_event_at": envelope.occurred_at,
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
    _recount_customer(data.customer_id, envelope.occurred_at)
    projection_events.labels(envelope.event_type, "applied").inc()


def _order_status_changed(envelope: Envelope, data) -> None:
    order = OperationOrder.objects.select_for_update().filter(source_order_id=data.order_id).first()
    if order is None:
        raise OutOfOrder(f"no projection for order {data.order_id}")
    if _fence(envelope, order.aggregate_version, "order") == "stale":
        return
    order.status = data.status
    order.aggregate_version = envelope.aggregate.version
    order.source_event_at = envelope.occurred_at
    order.save(update_fields=["status", "aggregate_version", "source_event_at", "updated_at"])
    _recount_customer(order.customer_id, envelope.occurred_at)
    projection_events.labels(envelope.event_type, "applied").inc()


def _stock_changed(envelope: Envelope, data) -> None:
    existing = InventoryProjection.objects.select_for_update().filter(product_code=data.product_code).first()
    if existing and _fence(envelope, existing.aggregate_version, "product") == "stale":
        return
    InventoryProjection.objects.update_or_create(
        product_code=data.product_code,
        defaults={"name": data.name, "stock_quantity": data.stock_quantity,
                  "aggregate_version": envelope.aggregate.version, "source_event_at": envelope.occurred_at},
    )
    projection_events.labels(envelope.event_type, "applied").inc()


def _customer_changed(envelope: Envelope, data) -> None:
    existing = CustomerProjection.objects.select_for_update().filter(source_customer_id=data.customer_id).first()
    if existing and _fence(envelope, existing.aggregate_version, "customer") == "stale":
        return
    CustomerProjection.objects.update_or_create(
        source_customer_id=data.customer_id,
        defaults={"name": data.name, "phone": data.phone,
                  "aggregate_version": envelope.aggregate.version, "source_event_at": envelope.occurred_at},
    )
    projection_events.labels(envelope.event_type, "applied").inc()


def _authz_changed(envelope: Envelope, data) -> None:
    incoming = envelope.aggregate.version
    sent_roles = "roles" in getattr(data, "model_fields_set", set())
    roles = sorted(set(data.roles)) if sent_roles else []
    existing = EmployeeAuthorization.objects.select_for_update().filter(subject_id=data.subject_id).first()
    if existing:
        if incoming < existing.authz_version:
            projection_events.labels(envelope.event_type, "stale").inc()
            return
        if incoming == existing.authz_version:
            same_state = (existing.role_active, existing.user_active) == (
                data.role_active, data.user_active
            )
            # a backfill re-sends a version it already sent, now carrying roles. that single enrichment is allowed, and only while nothing else about the state differs
            if same_state and sent_roles and not existing.roles_known:
                EmployeeAuthorization.objects.filter(pk=existing.pk).update(
                    roles=roles, roles_known=True
                )
                projection_events.labels(envelope.event_type, "applied").inc()
                return
            known = sorted(existing.roles or [])
            if same_state and (known == roles or not sent_roles):
                projection_events.labels(envelope.event_type, "idempotent").inc()
                return
            raise ProjectionConflict("authz", envelope.aggregate.id, incoming, envelope.event_id)
    # a newer event replaces the state it describes: keeping roles it never carried would pair a fresh flag with a role nobody re-confirmed
    defaults = {"authz_version": incoming, "role_active": data.role_active, "user_active": data.user_active, "roles": roles, "roles_known": sent_roles}
    EmployeeAuthorization.objects.update_or_create(subject_id=data.subject_id, defaults=defaults)
    projection_events.labels(envelope.event_type, "applied").inc()


def _recount_customer(customer_id: int, source_event_at=None) -> None:
    count = OperationOrder.objects.filter(customer_id=customer_id, status__in=ACTIVE_STATUSES).count()
    customer, created = CustomerProjection.objects.get_or_create(
        source_customer_id=customer_id,
        defaults={"active_orders_count": count, "source_event_at": source_event_at},
    )
    if created:
        return
    customer.active_orders_count = count
    # stamp the boundary only when the order path first materialised this customer; never
    # overwrite a customer_changed timestamp with a later order-status one
    if customer.source_event_at is None and source_event_at is not None:
        customer.source_event_at = source_event_at
    customer.save(update_fields=["active_orders_count", "source_event_at", "updated_at"])


def _record_expectation(envelope: Envelope, data) -> None:
    # one expectation per (run, aggregate); a repeated delivery is an idempotent upsert
    SnapshotExpectation.objects.update_or_create(
        snapshot_run_id=envelope.snapshot_run_id or "",
        aggregate_type=envelope.aggregate.type,
        aggregate_id=envelope.aggregate.id,
        defaults={"aggregate_version": envelope.aggregate.version, "payload": data.model_dump(mode="json")},
    )
    projection_events.labels(envelope.event_type, "snapshot").inc()


def _handle_control(envelope: Envelope, data) -> None:
    run = SnapshotRun.objects.select_for_update().filter(run_id=data.run_id).first()
    if data.phase == "started":
        # only a fresh or still-open run may (re)start; a completed run is immutable
        if run is not None and run.status == "completed":
            raise SnapshotProtocolError(f"run {data.run_id} already completed")
        SnapshotRun.objects.update_or_create(
            run_id=data.run_id, defaults={"status": "started", "as_of": data.as_of}
        )
    else:
        # completed must follow a started run exactly once — it never creates a run itself
        if run is None or run.status != "started":
            raise SnapshotProtocolError(f"completed without an open started run: {data.run_id}")
        run.status = "completed"
        run.expected_counts = dict(data.counts)
        run.as_of = data.as_of
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "expected_counts", "as_of", "completed_at"])
    projection_events.labels(envelope.event_type, "control").inc()
