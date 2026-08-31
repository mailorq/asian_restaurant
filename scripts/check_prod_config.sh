#!/usr/bin/env bash
# CI guard: the production compose must render from a clean checkout (no repo-root .env),
# inject the signing key only as a read-only secret file, keep the legacy in-storefront ops
# consumer out of production, and fail fast when any required production variable is missing.
# Wire into CI as a required check.
set -euo pipefail

# a throwaway key file only so `config` can resolve the secret source, and an empty env-file
# so nothing outside the explicit ${VAR:?} set can satisfy a required variable during interpolation
TMPKEY="$(mktemp)"; EMPTY_ENV="$(mktemp)"
trap 'rm -f "$TMPKEY" "$EMPTY_ENV"' EXIT
printf 'dummy\n' > "$TMPKEY"

# every mandatory ${VAR:?} referenced by a service that is part of the default production render
MANDATORY=(
  DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS DATABASE_URL REDIS_URL CART_REDIS_URL RABBITMQ_URL
  IDENTITY_JWT_KID IDENTITY_JWT_KEY_FILE
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  RABBITMQ_ADMIN_USER RABBITMQ_ADMIN_PASSWORD RABBITMQ_ERLANG_COOKIE
  STOREFRONT_MQ_PASSWORD OPERATIONS_MQ_PASSWORD BRIDGE_MQ_PASSWORD
  OPERATIONS_SECRET_KEY OPERATIONS_ALLOWED_HOSTS OPERATIONS_DATABASE_URL OPERATIONS_RABBITMQ_URL
  OPERATIONS_BRIDGE_CONSUME_URL OPERATIONS_BRIDGE_PUBLISH_URL
)

# CI dummy values (non-dev) so the render can complete; the negative loop below removes them one
# at a time to prove each is genuinely required
export DJANGO_SECRET_KEY=ci-django-secret
export DJANGO_ALLOWED_HOSTS=app.example.com
export DATABASE_URL=postgres://u:p@db:5432/storefront
export REDIS_URL=redis://redis:6379/1
export CART_REDIS_URL=redis://redis:6379/0
export RABBITMQ_URL=amqp://u:p@rabbitmq:5672/storefront
export IDENTITY_JWT_KID=prod-1 IDENTITY_JWT_KEY_FILE="$TMPKEY"
export POSTGRES_DB=storefront POSTGRES_USER=storefront POSTGRES_PASSWORD=ci-pg
export RABBITMQ_ADMIN_USER=ci RABBITMQ_ADMIN_PASSWORD=ci RABBITMQ_ERLANG_COOKIE=ci
export STOREFRONT_MQ_PASSWORD=ci OPERATIONS_MQ_PASSWORD=ci BRIDGE_MQ_PASSWORD=ci
export OPERATIONS_SECRET_KEY=ci-ops-secret OPERATIONS_ALLOWED_HOSTS=ops.example.com
export OPERATIONS_DATABASE_URL=postgres://u:p@operations-db:5432/operations
export OPERATIONS_RABBITMQ_URL=amqp://u:p@rabbitmq:5672/operations
export OPERATIONS_BRIDGE_CONSUME_URL=amqp://u:p@rabbitmq:5672/storefront
export OPERATIONS_BRIDGE_PUBLISH_URL=amqp://u:p@rabbitmq:5672/operations

PROD=(--env-file "$EMPTY_ENV" -f compose.yaml -f compose.prod.yaml)
rendered=$(docker compose "${PROD[@]}" config)
fail=0

# no dev fallbacks / no dev signing material / secret injected as a file / no inline key
grep -q "ops-dev-insecure" <<<"$rendered" && { echo "FAIL: ops-dev-insecure fallback present"; fail=1; }
grep -q "definitions.dev.json" <<<"$rendered" && { echo "FAIL: dev RabbitMQ definitions mounted"; fail=1; }
grep -q "jwt_private_key.pem" <<<"$rendered" && { echo "FAIL: dev signing-key mount present"; fail=1; }
grep -q "identity_jwt_private_key" <<<"$rendered" || { echo "FAIL: signing key not injected as a secret"; fail=1; }
grep -Eq "IDENTITY_JWT_PRIVATE_KEY:[[:space:]]*[^\"'[:space:]]" <<<"$rendered" && { echo "FAIL: inline private key in env"; fail=1; }

# legacy in-storefront projection consumer must not run in production
grep -q "run_ops_consumer" <<<"$rendered" && { echo "FAIL: legacy ops consumer present in production"; fail=1; }

grep -B3 -A3 'published: "9090"' <<<"$rendered" | grep -q 'host_ip: 127.0.0.1' || {
  echo "FAIL: prometheus 9090 not bound to loopback"; fail=1; }

# storefront Django processes (backend + relay) start under the production guard; ops services too
[ "$(grep -c 'DJANGO_PRODUCTION' <<<"$rendered")" -ge 2 ] || { echo "FAIL: DJANGO_PRODUCTION not set on all storefront services"; fail=1; }
[ "$(grep -c 'OPERATIONS_PRODUCTION' <<<"$rendered")" -ge 3 ] || { echo "FAIL: OPERATIONS_PRODUCTION not set on all ops services"; fail=1; }
grep -Eq "OPERATIONS_ALLOWED_HOSTS:[[:space:]]*'?\*'?[[:space:]]*$" <<<"$rendered" && { echo "FAIL: wildcard ALLOWED_HOSTS"; fail=1; }

# each mandatory variable being unset must make `config` fail (fail-closed, no silent default)
for var in "${MANDATORY[@]}"; do
  if env -u "$var" docker compose "${PROD[@]}" config >/dev/null 2>&1; then
    echo "FAIL: missing $var did not error"; fail=1
  fi
done

[ "$fail" -eq 0 ] && echo "prod config OK"
exit "$fail"
