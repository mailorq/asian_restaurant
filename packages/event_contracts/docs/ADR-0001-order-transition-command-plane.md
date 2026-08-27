# ADR-0001 — Order-transition command plane

## Status
Proposed (slice 1). The contract (`orders.transition.*.v1`), the `OperationCommand` state model,
and idempotent command creation / outcome application have landed with tests. The RabbitMQ
topology and permission deltas in **§Transport** are security-sensitive and are **not**
implemented until signed off.

## Context
Staff change order status today through the storefront's own employee API
(`POST /api/employee/orders/{id}/transition`), which writes the order directly. The operations
service is a separate read side: its own database, its own credentials, projections built from
versioned events. To let the new operations UI drive order state **without** giving operations
write access to the storefront database — and **without** a second direct write path — operations
issues an intent, the storefront (sole writer) applies it, and the outcome returns as a versioned
event.

## Decision — flow
1. **Operations API** accepts an employee JWT. `actor_id` is taken **only** from the verified JWT
   subject, never the request body. In one operations-DB transaction it idempotently creates an
   `OperationCommand`, an `OperationAuditLog`, and one `orders.transition.requested.v1` in
   `OperationsOutbox`. Operations never touches the storefront DB.
2. **Operations outbox relay** publishes the requested event with publisher confirms, then moves
   the command `pending → dispatched`.
3. **Storefront command consumer** is the ONLY writer. In one storefront-DB transaction it: dedups
   by `command_id` (CommandInbox); loads and `select_for_update`s the order; checks
   `expected_status` and transition validity; applies via `orders.service.transition` (which
   already emits the `order.status_changed` projection event to `OrderOutbox`); records the
   CommandInbox row with the serialized outcome; and writes the outcome event to `OrderOutbox`.
   A redelivered command replays the stored outcome instead of re-applying.
4. **Operations outcome consumer** validates the outcome against the command (`command_id`,
   `order_id`, `correlation_id`, allowed command type) **before** changing status, then finalizes.
5. **Timeout sweeper** moves a still-open command past `deadline_at` to `timed_out` (see below).

**Legacy path:** `POST /api/employee/orders/{id}/transition` and `/inventory/{id}/adjust` stay for
the existing storefront UI during migration but are marked legacy; the new operations UI uses only
the command plane, so no second write path originates from the new surface.

## Idempotency (option B)
Command creation is idempotent on a **client-supplied `idempotency_key`**, enforced by a unique
constraint `(actor_id, command_type, target, idempotency_key)`. A repeat with the same identity
**and** the same request payload returns the existing command (no new outbox row). The same key
with a **different** request payload is a conflict (HTTP 409). Different actors never collide on
the same key. `command_id` is server-minted and identifies the command instance; the idempotency
guard is the key, not `command_id` (a bare HTTP retry without a key would otherwise create a new
command).

## Command states & delivery uncertainty
```
pending         -> dispatched         requested event confirmed to the broker
pending         -> dispatch_failed    relay exhausted publish retries -> DLQ (delivery UNKNOWN)
dispatch_failed -> dispatched         successful re-publish (retry) confirmed
pending         -> timed_out          deadline passed, not yet dispatched
dispatched      -> timed_out          deadline passed, no outcome yet
{pending, dispatched, timed_out, dispatch_failed} -> succeeded | rejected   outcome applied
```
**Terminal = `{succeeded, rejected}` only** — a command is finished solely when the storefront
reports an outcome. Under **at-least-once** transport, neither a missing publisher confirm nor a
message landing in a DLQ proves the storefront never received the command: the publish may have
reached the broker/storefront just before a network error or a relay/process crash, so a late
outcome is still possible. Absence of confirmation is an **unknown delivery state, not proof of
non-delivery**. `dispatch_failed` and `timed_out` are therefore **non-terminal** unknown-delivery
states that raise alerts and drive retry/reconciliation; a late `succeeded`/`rejected` outcome
finalizes the command from any non-terminal state. There is no terminal `failed` state and no
`mark_failed()` terminal transition. The UI must show `dispatch_failed`/`timed_out` as "delivery
unconfirmed — reconciling", never as "the storefront did nothing".

## Contract (this package)
Events — `schema_version` 1, shared `Envelope`, aggregate `(order, order_id)`:

| event | data |
|-------|------|
| `orders.transition.requested.v1` | `command_id`, `actor_id`(>0), `order_id`(>0), `expected_status`, `target_status` (≠ expected), `reason` (≤255) |
| `orders.transition.succeeded.v1` | `command_id`, `order_id`, `from_status`, `status` (≠ from_status) |
| `orders.transition.rejected.v1`  | `command_id`, `order_id`, `reject_code`, `current_status`, `detail` (≤255) |

Enforced invariants (`parse_event` + model validators, with negative tests):
- **producer**: requested MUST be `operations`; succeeded/rejected MUST be `storefront`.
- **rejected**: `order_not_found` ⇒ `current_status` absent; every other code ⇒ present.
- **succeeded**: `status` ≠ `from_status`.
- `reason` / `detail` ≤ 255, matching storefront `OrderStatusHistory.note`.
- `aggregate.version` is traceability only; the concurrency guard is `expected_status` under lock.
- **outcome envelope**: `correlation_id` MUST equal the originating command's; `causation_id` MUST
  be the requested event's `event_id`. (Enforced where the outcome is emitted/consumed — next
  slice.)

## Inbox / outbox
- **CommandInbox** (storefront) stores, per `command_id`: the request `event_id`,
  `correlation_id`, and the **serialized outcome**. A redelivered command replays that outcome
  verbatim and never re-applies the transition.
- The **outcome consumer** (operations) checks `command_id`, `order_id`, `correlation_id`, an
  allowed command type, **and that the outcome matches the requested transition** (succeeded:
  `from_status == expected_status` and `status == target_status`; rejected: `current_status` is
  consistent with the reject code and `expected_status`) before changing status; a mismatch is
  rejected, not applied — an outcome for a different target can never finalize the command.
- **OperationsOutbox** (next iteration) must persist the envelope inputs as first-class columns —
  `event_id`, `correlation_id`, `causation_id`, `aggregate` id/version, `producer`, `command_id` —
  and the relay assembles the envelope from those, **not** by re-reading an unvalidated `payload`.

## Transport — NEEDS SIGN-OFF (RabbitMQ topology + permissions)
Vhosts today: `storefront` (`storefront_app`), `operations` (`operations_consumer`), and
`operations_bridge` spanning both. The command plane crosses vhosts in both directions.
- **Command (operations → storefront):** operations outbox relay → new `operations.commands` topic
  exchange on the **operations** vhost (within `^operations\.`) → new cross-vhost **command relay**
  (mirrors `operations_bridge`) → `commands` exchange on the **storefront** vhost → storefront
  command consumer's durable `commands.orders` queue (+ retry/DLQ, same shape as elsewhere).
- **Outcome (storefront → operations):** storefront outbox → existing `orders` exchange →
  **existing bridge, extended** with the two outcome types → new `operations.commands.outcomes`
  exchange on the operations vhost → operations outcome consumer.

Permission deltas to review (`ops/rabbitmq/definitions.dev.json` + `provision.sh`):
`operations_consumer` gains `operations.commands` and `operations.commands.outcomes` (already
inside `^operations\.`); a new cross-vhost relay principal scoped to `commands`/`operations.commands`
on the storefront vhost; `storefront_app` reads/binds `commands`. Alternative — a dedicated
`commands` vhost — rejected for slice 1 (more moving parts; the split keeps each app on its vhost).

## Reliability & observability
Publisher confirms; transactional outbox + CommandInbox dedup; bounded retry via a TTL queue that
dead-letters to a DLQ (poison / retries-exhausted). Exhausting relay/consumer retries moves the
command to the non-terminal `dispatch_failed` and raises a DLQ-depth alert — it never asserts the
command did not run. `deadline_at` sweeps a still-open command to the non-terminal `timed_out`.
Metrics: command-outbox oldest-pending age, command state counters, `timed_out` /
`dispatch_failed` gauges, DLQ depth, dispatch/outcome latency.

## Tests
- **contract** — this package (producer, status rules, length caps, aggregate/id match).
- **unit** — creation idempotency (same / conflict / different-actor); outcome application incl.
  `timed_out → late succeeded`, terminal-guard, correlation/order mismatch.
- **integration** (next slice) — end-to-end; duplicate command; stale status; retry; reject.
- **failure/retry** (next slice) — broker down keeps the outbox pending; exhausted retries → DLQ →
  non-terminal `dispatch_failed`, from which a late outcome still finalizes the command.

## Remaining work (after transport sign-off)
Operations: command API endpoint (JWT → `create_transition_command`); `publish_operations_outbox`
relay with dispatched-marking; outcome consumer (`apply_transition_outcome`); timeout sweeper;
metrics. Storefront: `CommandInbox` model + migration; `run_command_consumer`; outcome events
emitted by the service; legacy endpoints annotated. Transport: exchanges / queues / permissions per
§Transport; the command relay. Then integration + failure/retry tests.
