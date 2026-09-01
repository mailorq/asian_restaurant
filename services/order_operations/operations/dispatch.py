"""
single entry point for consumed events

inbox dedup, outcome application and projection share one transaction, so a failure anywhere
rolls the inbox record back and the redelivery is handled again instead of being skipped
"""

from django.db import transaction
from event_contracts import (
    EVENT_ORDER_TRANSITION_REJECTED,
    EVENT_ORDER_TRANSITION_SUCCEEDED,
    Envelope,
)

from operations import projection
from operations.commands import apply_transition_outcome

OUTCOME_EVENTS = frozenset({EVENT_ORDER_TRANSITION_SUCCEEDED, EVENT_ORDER_TRANSITION_REJECTED})


@transaction.atomic
def handle(envelope: Envelope, data) -> bool:
    """returns False when the event was already handled"""
    if not projection.remember(envelope):
        return False
    if envelope.event_type in OUTCOME_EVENTS:
        apply_transition_outcome(data, correlation_id=envelope.correlation_id)
    else:
        projection.project(envelope, data)
    return True
