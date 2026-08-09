import datetime as dt
import uuid

from django.core.management.base import BaseCommand
from event_contracts import EVENT_ORDER_CREATED

from operations import messaging


class Command(BaseCommand):
    help = "Publish a versioned test order.created event to operations.events (shadow verification)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--order-id", type=int, default=999001)
        parser.add_argument("--customer-id", type=int, default=42)

    def handle(self, *args, **options) -> None:
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": EVENT_ORDER_CREATED,
            "schema_version": 1,
            "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
            "producer": "test",
            "aggregate": {"type": "order", "id": str(options["order_id"]), "version": 1},
            "correlation_id": str(uuid.uuid4()),
            "causation_id": None,
            "trace_id": None,
            "data": {
                "order_id": options["order_id"],
                "customer_id": options["customer_id"],
                "status": "created",
                "total": "300.00",
                "recipient_name": "Тест",
                "phone": "+380671111111",
                "address": "ул. Тестовая 1",
                "address_verified": False,
                "payment_method": "cash",
                "items": [
                    {
                        "source_product_id": 1,
                        "product_code": "dish_1",
                        "name": "Рамен",
                        "quantity": 2,
                        "unit_price": "150.00",
                        "line_total": "300.00",
                    }
                ],
            },
        }
        connection = messaging.connect()
        try:
            channel = connection.channel()
            messaging.declare_topology(channel)
            channel.confirm_delivery()
            messaging.publish_envelope(channel, messaging.EXCHANGE, EVENT_ORDER_CREATED, envelope)
        finally:
            connection.close()
        self.stdout.write(self.style.SUCCESS(f"published {EVENT_ORDER_CREATED} order_id={options['order_id']}"))
