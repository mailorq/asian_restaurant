# Order Operations service

Independent service for restaurant staff. Owns only its own read models and
command state; it never imports storefront ORM and never touches the storefront
database. Fed by versioned domain events over RabbitMQ.

## Data ownership

- Storefront is the single writer of `Order`, `Product/stock`, customer identity
  and checkout invariants.
- Operations builds projections from events and (Phase 3) requests changes via
  async commands; it is never a second writer of order status.
- Separate databases, separate roles: `ops_user` cannot authenticate to the
  storefront DB and vice versa. No shared Django session, `SECRET_KEY` or creds.

## Contracts

Versioned Pydantic contracts live in `packages/event_contracts` (no Django). A
single envelope (`event_id`, `event_type`, `schema_version`, `occurred_at`,
`producer`, `aggregate{type,id,version}`, `correlation_id`, `causation_id`,
`trace_id`, `data`) wraps every event and command. Backward-compatible additions
are ignored by older consumers; breaking changes require a new event version.

## Processes

| Process | Command |
|---|---|
| API (read-only, shadow) | `python manage.py runserver` → `/ops-api/` |
| Projection consumer | `python manage.py run_operations_consumer` |
| Legacy bridge (temporary) | `python manage.py bridge_storefront_events` |
| Test event (verification) | `python manage.py publish_test_event --order-id N --customer-id M` |

## Run (dev)

```bash
# from the repo root
docker compose up -d --build operations-db operations-api operations-consumer

# migrate + inspect
docker compose exec operations-api python manage.py migrate
docker compose exec operations-db psql -U ops_user -d operations -c "\dt"

# tests
docker compose exec operations-api sh -lc "cd /packages/event_contracts && python -m pytest"
docker compose exec operations-api sh -lc "cd /app && pytest"

# shadow round-trip
docker compose exec operations-api python manage.py publish_test_event --order-id 555999 --customer-id 88
docker compose exec operations-db psql -U ops_user -d operations -c \
  "SELECT source_order_id, status FROM operations_operationorder WHERE source_order_id=555999;"
```

## Environment

| Variable | Purpose |
|---|---|
| `OPERATIONS_DATABASE_URL` | operations DB (ops role); never the storefront DB |
| `OPERATIONS_SECRET_KEY` | own secret, not shared with storefront |
| `OPERATIONS_RABBITMQ_URL` | event/command bus |
| `IDENTITY_JWKS_URL` | Identity public keys for JWT verification (Phase 3) |

## Auth (design; wired in Phase 3)

Identity/storefront remains the sole owner of employee role and the
`restaurant_employee` group. Operations does not read `auth_user`/`groups`. Staff
present a short-lived, asymmetrically signed JWT (`sub`, `roles`, `authz_version`,
`jti`, `exp`); Operations verifies it against Identity's public keys (JWKS). Role
revocation takes effect within the token TTL plus an
`identity.employee_role_changed.v1` event. The actor is always taken from the
verified token, never from a browser-supplied id.

## Status

Phase 1 (foundation, shadow mode). Not wired to the frontend; legacy
`/api/employee/*` remains the live path until later phases pass their checklists.
