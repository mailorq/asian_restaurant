#!/usr/bin/env bash
# CI guard: the production compose must render without dev fallbacks, must inject the
# signing key as a secret file (never an env var), and must fail fast when a required
# secret is missing. Wire into CI as a required check.
set -euo pipefail

# a throwaway key file only so `config` can resolve the secret source during rendering,
# and an empty env-file so the local .env never satisfies a required variable
TMPKEY="$(mktemp)"; EMPTY_ENV="$(mktemp)"
trap 'rm -f "$TMPKEY" "$EMPTY_ENV"' EXIT
printf 'dummy\n' > "$TMPKEY"

# dummy non-dev secrets so `config` can render
export RABBITMQ_ADMIN_USER=ci RABBITMQ_ADMIN_PASSWORD=ci RABBITMQ_ERLANG_COOKIE=ci
export STOREFRONT_MQ_PASSWORD=ci OPERATIONS_MQ_PASSWORD=ci BRIDGE_MQ_PASSWORD=ci
export OPERATIONS_SECRET_KEY=ci-secret OPERATIONS_ALLOWED_HOSTS=ops.example.com
export OPERATIONS_DATABASE_URL=postgres://u:p@db/ops
export OPERATIONS_RABBITMQ_URL=amqp://u:p@rabbitmq:5672/operations
export OPERATIONS_BRIDGE_CONSUME_URL=amqp://u:p@rabbitmq:5672/storefront
export OPERATIONS_BRIDGE_PUBLISH_URL=amqp://u:p@rabbitmq:5672/operations
export IDENTITY_JWT_KID=prod-1 IDENTITY_JWT_KEY_FILE="$TMPKEY"

PROD=(--env-file "$EMPTY_ENV" -f compose.yaml -f compose.prod.yaml)
rendered=$(docker compose "${PROD[@]}" config)
fail=0

grep -q "ops-dev-insecure" <<<"$rendered" && { echo "FAIL: ops-dev-insecure fallback present"; fail=1; }
grep -q "definitions.dev.json" <<<"$rendered" && { echo "FAIL: dev RabbitMQ definitions mounted"; fail=1; }
grep -q "jwt_private_key.pem" <<<"$rendered" && { echo "FAIL: dev signing-key mount present"; fail=1; }
grep -q "identity_jwt_private_key" <<<"$rendered" || { echo "FAIL: signing key not injected as a secret"; fail=1; }
grep -Eq "IDENTITY_JWT_PRIVATE_KEY:[[:space:]]*[^\"'[:space:]]" <<<"$rendered" && { echo "FAIL: inline private key in env"; fail=1; }
[ "$(grep -c 'OPERATIONS_PRODUCTION' <<<"$rendered")" -ge 3 ] || { echo "FAIL: OPERATIONS_PRODUCTION not set on all ops services"; fail=1; }
grep -Eq "OPERATIONS_ALLOWED_HOSTS:[[:space:]]*'?\*'?[[:space:]]*$" <<<"$rendered" && { echo "FAIL: wildcard ALLOWED_HOSTS"; fail=1; }

# each required secret being unset must make `config` fail
for var in OPERATIONS_SECRET_KEY IDENTITY_JWT_KEY_FILE IDENTITY_JWT_KID; do
  if env -u "$var" docker compose "${PROD[@]}" config >/dev/null 2>&1; then
    echo "FAIL: missing $var did not error"; fail=1
  fi
done

[ "$fail" -eq 0 ] && echo "prod config OK"
exit "$fail"
