#!/usr/bin/env bash
# CI guard: the production compose must render without dev fallbacks, and must fail
# fast when a required secret is missing. Wire into CI as a required check.
set -euo pipefail

# dummy non-dev secrets so `config` can render
export RABBITMQ_ADMIN_USER=ci RABBITMQ_ADMIN_PASSWORD=ci RABBITMQ_ERLANG_COOKIE=ci
export STOREFRONT_MQ_PASSWORD=ci OPERATIONS_MQ_PASSWORD=ci BRIDGE_MQ_PASSWORD=ci
export OPERATIONS_SECRET_KEY=ci-secret OPERATIONS_ALLOWED_HOSTS=ops.example.com
export OPERATIONS_DATABASE_URL=postgres://u:p@db/ops
export OPERATIONS_RABBITMQ_URL=amqp://u:p@rabbitmq:5672/operations
export OPERATIONS_BRIDGE_CONSUME_URL=amqp://u:p@rabbitmq:5672/storefront
export OPERATIONS_BRIDGE_PUBLISH_URL=amqp://u:p@rabbitmq:5672/operations

PROD=(-f compose.yaml -f compose.prod.yaml)
rendered=$(docker compose "${PROD[@]}" config)
fail=0

grep -q "ops-dev-insecure" <<<"$rendered" && { echo "FAIL: ops-dev-insecure fallback present"; fail=1; }
grep -q "definitions.dev.json" <<<"$rendered" && { echo "FAIL: dev RabbitMQ definitions mounted"; fail=1; }
[ "$(grep -c 'OPERATIONS_PRODUCTION' <<<"$rendered")" -ge 3 ] || { echo "FAIL: OPERATIONS_PRODUCTION not set on all ops services"; fail=1; }
grep -Eq "OPERATIONS_ALLOWED_HOSTS:[[:space:]]*'?\*'?[[:space:]]*$" <<<"$rendered" && { echo "FAIL: wildcard ALLOWED_HOSTS"; fail=1; }

# a required secret being unset must make `config` fail
if OPERATIONS_SECRET_KEY= docker compose "${PROD[@]}" config >/dev/null 2>&1; then
  echo "FAIL: missing OPERATIONS_SECRET_KEY did not error"; fail=1
fi

[ "$fail" -eq 0 ] && echo "prod config OK"
exit "$fail"
