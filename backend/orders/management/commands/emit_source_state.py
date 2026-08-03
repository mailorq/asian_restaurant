from django.core.management.base import BaseCommand
from django.db import transaction

from accounts import service as accounts_service
from accounts.models import User
from menu import inventory
from menu.models import Product


class Command(BaseCommand):
    help = "Emit current product/customer state through the outbox: --snapshot for reconciliation, else live seeding."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--snapshot", action="store_true", help="emit snapshot events (reconciliation), not live seeds")

    def handle(self, *args, **options) -> None:
        snapshot = options["snapshot"]
        products = customers = 0
        with transaction.atomic():
            for product in Product.objects.all().iterator():
                inventory.emit_state(product, snapshot=snapshot)
                products += 1
            for user in User.objects.exclude(customer_version=0).iterator():
                accounts_service.emit_state(user, snapshot=snapshot)
                customers += 1
        mode = "snapshot" if snapshot else "live"
        self.stdout.write(self.style.SUCCESS(f"emitted {mode} state: {products} products, {customers} customers"))
