import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Aggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    id: str
    version: int = Field(ge=1)


class Envelope(BaseModel):
    """Transport-agnostic message envelope shared by every event and command.

    `extra="ignore"` on the envelope lets a newer producer add top-level fields
    without breaking an older consumer; `data` is validated by the per-type model.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: uuid.UUID
    event_type: str
    schema_version: int = Field(ge=1)
    occurred_at: dt.datetime
    producer: str
    aggregate: Aggregate
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    trace_id: str | None = None
    # set by an adapter that relays another service's event; producer stays the origin
    relayed_by: str | None = None
    # a snapshot re-states current aggregate state for reconciliation; consumers must
    # treat it as an upsert of expected state, not as a new version-fenced change
    snapshot: bool = False
    # ties a snapshot event (and its control events) to one reconciliation run
    snapshot_run_id: str | None = None
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware (UTC)")
        return value.astimezone(dt.UTC)
