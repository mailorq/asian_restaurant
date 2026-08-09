#!/usr/bin/env bash
# Real end-to-end reconciliation in an ISOLATED Compose project with its own volumes:
#   source models -> emit_source_state -> publish_outbox -> bridge -> consumer -> reconcile
# Never touches the shared dev/staging project. No manual pika publishing.
set -euo pipefail

if [ "${E2E_ALLOW_DESTRUCTIVE:-0}" != "1" ]; then
  echo "refusing to run: this test creates and destroys an isolated stack." >&2
  echo "re-run with E2E_ALLOW_DESTRUCTIVE=1" >&2
  exit 2
fi

PROJ=ar_e2e
CO=(-p "$PROJ" -f compose.yaml -f compose.override.yaml -f compose.e2e.yaml)
dc() { docker compose "${CO[@]}" "$@"; }
be() { dc exec -T backend "$@"; }
ops() { dc exec -T operations-api "$@"; }
bridge_ready() { dc logs operations-bridge 2>&1 | grep -q 'storefront bridge:'; }
order_projected() { ops python manage.py shell -c "import sys; from operations.models import OperationOrder; sys.exit(0 if OperationOrder.objects.exists() else 1)"; }

cleanup() { echo "== teardown (only $PROJ) =="; dc down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

wait_for() {  # wait_for <label> <cmd...>
  local label="$1"; shift
  for _ in $(seq 1 60); do "$@" >/dev/null 2>&1 && { echo "ready: $label"; return 0; }; sleep 2; done
  echo "timeout waiting for: $label" >&2; return 1
}

echo "== bring up isolated stack =="
dc up -d db redis rabbitmq operations-db operations-api operations-consumer operations-bridge backend >/dev/null
wait_for rabbitmq dc exec -T rabbitmq rabbitmq-diagnostics -q ping
wait_for backend-migrated be python manage.py migrate --check
wait_for operations-migrated ops python manage.py migrate --check

echo "== declare storefront 'orders' exchange, then rebind bridge =="
be python manage.py shell <<'PY'
from orders import messaging
messaging.declare_topology(messaging.connect().channel())
print("orders topology declared")
PY
dc restart operations-bridge >/dev/null
wait_for bridge-bound bridge_ready

echo "== seed source models (product, customer, order) =="
be python manage.py shell <<'PY'
from decimal import Decimal
from django.contrib.auth import get_user_model
from menu.models import Product
from orders.models import DeliveryAddress, Order, OrderItem, OrderStatusHistory

User = get_user_model()
p = Product.objects.create(code="e2e_dish", category="dish", name="E2E Рамен",
                           price=Decimal("50.00"), stock_quantity=10, version=1)
u = User.objects.create_user(username="+79995550000", phone="+79995550000",
                             password="Pass!2345", first_name="Иван", customer_version=1)
addr = DeliveryAddress.objects.create(user=u, address="ул. E2E 1", is_verified=True)
o = Order.objects.create(user=u, status="created", payment_method="cash", phone=u.phone,
                         contact_name="Иван", delivery_address=addr, total=Decimal("100.00"),
                         idempotency_key="e2e-key", source_cart_id="e2e", source_cart_version=1)
OrderItem.objects.create(order=o, product=p, product_name=p.name,
                         unit_price=Decimal("50.00"), quantity=2, line_total=Decimal("100.00"))
OrderStatusHistory.objects.create(order=o, from_status="", to_status="created", note="seed")
print(f"seeded product={p.code} user={u.id} order={o.id}")
PY

echo "== emit live state + snapshots, then relay through the outbox =="
be python manage.py emit_source_state
be python manage.py emit_source_state --snapshot
for _ in 1 2 3 4 5; do be python manage.py publish_outbox; done

echo "== wait for projections, then reconcile (expect unexplained=0) =="
wait_for order-projected order_projected
ops python manage.py reconcile
