#!/usr/bin/env bash
# Real end-to-end reconciliation:
#   source models -> emit_source_state -> publish_outbox (relay) -> bridge -> consumer -> reconcile
# No manual pika publishing. Run from the repo root with Docker available.
set -euo pipefail

dc() { docker compose "$@"; }
exec_be() { dc -f compose.yaml -f compose.override.yaml exec -T backend "$@"; }
exec_ops() { dc exec -T operations-api "$@"; }

echo "== bring up full stack =="
dc up -d db redis rabbitmq operations-db operations-api operations-consumer operations-bridge >/dev/null
dc -f compose.yaml -f compose.override.yaml up -d backend >/dev/null
sleep 8

echo "== reset operations read side for a clean assertion =="
exec_ops python manage.py shell <<'PY'
from operations.models import (CustomerProjection, InboxEvent, InventoryProjection,
    OperationOrder, OperationOrderItem, SnapshotExpectation)
for M in (OperationOrderItem, OperationOrder, InventoryProjection, CustomerProjection, InboxEvent, SnapshotExpectation):
    M.objects.all().delete()
print("operations read side cleared")
PY

echo "== declare storefront 'orders' exchange and rebind bridge =="
exec_be python manage.py shell <<'PY'
from orders import messaging
ch = messaging.connect().channel()
messaging.declare_topology(ch)
print("orders topology declared")
PY
dc restart operations-bridge >/dev/null
sleep 5

echo "== seed source models (product, customer, order) =="
exec_be python manage.py shell <<'PY'
from decimal import Decimal
from django.contrib.auth import get_user_model
from menu.models import Product
from orders.models import DeliveryAddress, Order, OrderItem, OrderStatusHistory

User = get_user_model()
old = User.objects.filter(username="+79995550000").first()
if old:
    Order.objects.filter(user=old).delete()          # cascades items + history
    DeliveryAddress.objects.filter(user=old).delete()
    old.delete()
Product.objects.filter(code="e2e_dish").delete()

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
exec_be python manage.py emit_source_state
exec_be python manage.py emit_source_state --snapshot
for _ in 1 2 3 4 5; do exec_be python manage.py publish_outbox; done
sleep 6

echo "== reconcile (expect unexplained=0) =="
exec_ops python manage.py reconcile
