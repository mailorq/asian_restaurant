import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts import service as accounts_service
from accounts.models import User
from menu import inventory
from menu.models import Product
from orders import service as order_service
from orders.models import Order, OrderOutbox


class Command(BaseCommand):
    help = "Emit current product/customer/order state through the outbox: --snapshot for a reconciliation run, else live seeding."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--snapshot", action="store_true", help="emit a fenced snapshot run (start/aggregates/completed)")

    def handle(self, *args, **options) -> None:
        snapshot = options["snapshot"]
        run_id = uuid.uuid4().hex if snapshot else ""
        products = customers = orders = 0
        with transaction.atomic():
            if snapshot:
                self._control(run_id, "started")
            for product in Product.objects.all().iterator():
                inventory.emit_state(product, snapshot=snapshot, run_id=run_id)
                products += 1
            for user in User.objects.exclude(customer_version=0).iterator():
                accounts_service.emit_state(user, snapshot=snapshot, run_id=run_id)
                customers += 1
            for order in Order.objects.iterator():
                order_service.emit_order_state(order, snapshot=snapshot, run_id=run_id)
                orders += 1
            if snapshot:
                self._control(run_id, "completed", {"product": products, "customer": customers, "order": orders})
        mode = f"snapshot run {run_id}" if snapshot else "live"
        self.stdout.write(
            self.style.SUCCESS(f"emitted {mode}: {products} products, {customers} customers, {orders} orders")
        )

    def _control(self, run_id: str, phase: str, counts: dict | None = None) -> None:
        OrderOutbox.objects.create(
            aggregate_id=run_id,
            aggregate_version=1,
            event_type="snapshot.control",
            routing_key="snapshot.control",
            snapshot_run_id=run_id,
            payload={"run_id": run_id, "phase": phase, "counts": counts or {}},
        )
