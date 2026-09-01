"""storefront application of operations commands, the only writer of order state

inbox row, order change and outcome commit together; a redelivery replays the stored outcome
"""

import uuid
from functools import partial

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from event_contracts import (
    EVENT_ORDER_TRANSITION_REJECTED,
    EVENT_ORDER_TRANSITION_SUCCEEDED,
    OrderTransitionRejectedData,
    OrderTransitionRequestedData,
    OrderTransitionSucceededData,
    TransitionRejectCode,
)

from accounts.models import has_operations_role
from orders import service as order_service
from orders.models import CommandInbox, Order, OrderOutbox, OrderStatusHistory

ROUTING_KEYS = {
    EVENT_ORDER_TRANSITION_SUCCEEDED: "order.transition_succeeded",
    EVENT_ORDER_TRANSITION_REJECTED: "order.transition_rejected",
}


class Outcome:
    """result of applying a command, either freshly produced or replayed from the inbox"""

    def __init__(self, event_type: str, data: dict, *, replayed: bool = False) -> None:
        self.event_type = event_type
        self.data = data
        self.replayed = replayed

    @property
    def rejected(self) -> bool:
        return self.event_type == EVENT_ORDER_TRANSITION_REJECTED

    @property
    def reject_code(self) -> str:
        return self.data.get("reject_code", "")


def _order_version(order: Order | None) -> int:
    # aggregate version is the status history length; envelopes require >= 1
    if order is None:
        return 1
    return max(1, OrderStatusHistory.objects.filter(order=order).count())


def _actor(data: OrderTransitionRequestedData):
    # locked so a concurrent revocation cannot interleave with the check below
    return get_user_model().objects.select_for_update().filter(pk=data.actor_id).first()


def _authorized(actor, data: OrderTransitionRequestedData) -> bool:
    # token authority may already be revoked, so the writer re-checks it
    return bool(
        actor
        and actor.is_active
        and has_operations_role(actor)
        and actor.authz_version == data.actor_authz_version
    )


def _record(data: OrderTransitionRequestedData, *, request_event_id, correlation_id,
            event_type: str, payload: dict, order: Order | None) -> Outcome:
    outcome_event_id = uuid.uuid4()
    CommandInbox.objects.create(
        command_id=data.command_id,
        request_event_id=request_event_id,
        correlation_id=correlation_id,
        outcome_event_id=outcome_event_id,
        outcome_type=event_type,
        outcome_data=payload,
    )
    OrderOutbox.objects.create(
        event_id=outcome_event_id,
        aggregate_id=str(data.order_id),
        aggregate_version=_order_version(order),
        event_type=event_type,
        routing_key=ROUTING_KEYS[event_type],
        correlation_id=correlation_id,
        causation_id=request_event_id,
        payload=payload,
    )
    return Outcome(event_type, payload)


def _reject(data: OrderTransitionRequestedData, *, request_event_id, correlation_id,
            code: TransitionRejectCode, order: Order | None = None,
            current_status: str | None = None, detail: str = "") -> Outcome:
    payload = OrderTransitionRejectedData(
        command_id=data.command_id, order_id=data.order_id, reject_code=code,
        current_status=current_status, detail=detail,
    ).model_dump(mode="json")
    return _record(data, request_event_id=request_event_id, correlation_id=correlation_id,
                   event_type=EVENT_ORDER_TRANSITION_REJECTED, payload=payload, order=order)


@transaction.atomic
def apply_transition_command(data: OrderTransitionRequestedData, *, request_event_id,
                             correlation_id) -> Outcome:
    """applies one transition command, idempotent by command_id"""
    seen = CommandInbox.objects.filter(command_id=data.command_id).first()
    if seen is not None:
        # recorded outcome replays verbatim, including after expiry
        return Outcome(seen.outcome_type, seen.outcome_data, replayed=True)

    reject = partial(_reject, data, request_event_id=request_event_id,
                     correlation_id=correlation_id)

    # fixed order; the first three run before the order is loaded
    if data.expires_at <= timezone.now():
        return reject(code=TransitionRejectCode.command_expired,
                      detail="command expired before it was applied")

    actor = _actor(data)
    if not _authorized(actor, data):
        return reject(code=TransitionRejectCode.actor_not_authorized,
                      detail="actor is no longer authorized")

    order = Order.objects.select_for_update().filter(pk=data.order_id).first()
    if order is None:
        return reject(code=TransitionRejectCode.order_not_found)
    if order.status != data.expected_status:
        return reject(code=TransitionRejectCode.stale_status, order=order,
                      current_status=order.status, detail=f"order is at {order.status}")
    if not order.can_transition_to(data.target_status):
        return reject(code=TransitionRejectCode.invalid_transition, order=order,
                      current_status=order.status,
                      detail=f"{order.status} to {data.target_status} is not allowed")

    from_status = order.status
    order_service.transition(
        order, data.target_status, changed_by=actor, note=data.reason[:255],
        expected_status=data.expected_status,
    )
    payload = OrderTransitionSucceededData(
        command_id=data.command_id, order_id=data.order_id,
        from_status=from_status, status=data.target_status,
    ).model_dump(mode="json")
    return _record(data, request_event_id=request_event_id, correlation_id=correlation_id,
                   event_type=EVENT_ORDER_TRANSITION_SUCCEEDED, payload=payload,
                   order=Order.objects.get(pk=order.pk))
