#!/usr/bin/env bash
# Ephemeral production-bootstrap smoke test in an isolated Compose project with its own
# volumes: boot a bare broker (no dev definitions), run the rabbitmq-provision one-shot,
# verify vhosts/users/permissions, the three service accounts connect, and the prometheus
# plugin is live. Tears down ONLY this project's volumes at the end.
set -euo pipefail

PROJ=ar_prodsmoke
PROD=(-p "$PROJ" -f compose.yaml -f compose.prod.yaml)
dc() { docker compose "${PROD[@]}" "$@"; }

# dummy secrets (this is a throwaway broker)
export RABBITMQ_ADMIN_USER=admin RABBITMQ_ADMIN_PASSWORD=smoke-admin RABBITMQ_ERLANG_COOKIE=smoke-cookie
export STOREFRONT_MQ_PASSWORD=smoke-store OPERATIONS_MQ_PASSWORD=smoke-ops BRIDGE_MQ_PASSWORD=smoke-bridge
export OPERATIONS_SECRET_KEY=smoke-secret-key OPERATIONS_ALLOWED_HOSTS=ops.local
export OPERATIONS_DATABASE_URL=postgres://u:p@operations-db:5432/operations
export OPERATIONS_RABBITMQ_URL=amqp://operations_consumer:smoke-ops@rabbitmq:5672/operations
export OPERATIONS_BRIDGE_CONSUME_URL=amqp://operations_bridge:smoke-bridge@rabbitmq:5672/storefront
export OPERATIONS_BRIDGE_PUBLISH_URL=amqp://operations_bridge:smoke-bridge@rabbitmq:5672/operations

cleanup() { echo "== teardown (only $PROJ volumes) =="; dc down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== boot bare broker (no dev definitions) =="
dc up -d rabbitmq >/dev/null
# -u rabbitmq: exec defaults to root and HOME is the data dir, so a cli that runs before the
# server wrote .erlang.cookie creates it root-owned, and the server dies reading its own cookie
for _ in $(seq 1 30); do dc exec -T -u rabbitmq rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1 && break; sleep 2; done

echo "== run rabbitmq-provision one-shot =="
dc run --rm rabbitmq-provision

echo "== vhosts / users / permissions =="
dc exec -T rabbitmq rabbitmqctl list_vhosts
dc exec -T rabbitmq rabbitmqctl list_users
dc exec -T rabbitmq rabbitmqctl list_permissions -p operations

echo "== three service accounts connect to their vhosts =="
dc run --rm --no-deps --entrypoint python operations-api - <<'PY'
import pika
targets = {
    "storefront_app@storefront": "amqp://storefront_app:smoke-store@rabbitmq:5672/storefront",
    "operations_consumer@operations": "amqp://operations_consumer:smoke-ops@rabbitmq:5672/operations",
    "operations_bridge@storefront": "amqp://operations_bridge:smoke-bridge@rabbitmq:5672/storefront",
}
for label, url in targets.items():
    pika.BlockingConnection(pika.URLParameters(url)).close()
    print(f"OK {label}")
PY

echo "== prometheus plugin live on :15692 (network-internal) =="
dc run --rm --no-deps --entrypoint python operations-api - <<'PY'
import urllib.request
body = urllib.request.urlopen("http://rabbitmq:15692/metrics", timeout=5).read().decode()
assert "rabbitmq_" in body, "rabbitmq_prometheus metrics not exposed"
print("OK rabbitmq_prometheus metrics present")
PY

echo "SMOKE OK"
