import json

import pika
from django.conf import settings

EXCHANGE = "operations.events"
QUEUE = "operations.projection"
DLX = "operations.dlx"
DLQ = "operations.projection.dlq"
RETRY_EXCHANGE = "operations.retry"
RETRY_QUEUE = "operations.projection.retry"
RETRY_TTL_MS = 5000
MAX_RETRIES = 5

BOUND_EVENTS = (
    "orders.order.created.v1",
    "orders.order.status_changed.v1",
    "inventory.stock_changed.v1",
    "identity.customer_changed.v1",
    "operations.snapshot.control.v1",
)


def connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))


def declare_topology(channel) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=RETRY_EXCHANGE, exchange_type="topic", durable=True)

    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_bind(queue=DLQ, exchange=DLX, routing_key="#")

    channel.queue_declare(
        queue=RETRY_QUEUE,
        durable=True,
        arguments={"x-message-ttl": RETRY_TTL_MS, "x-dead-letter-exchange": EXCHANGE},
    )
    channel.queue_bind(queue=RETRY_QUEUE, exchange=RETRY_EXCHANGE, routing_key="#")

    channel.queue_declare(queue=QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX})
    for routing_key in BOUND_EVENTS:
        channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=routing_key)


def publish_envelope(channel, exchange: str, routing_key: str, envelope: dict, headers: dict | None = None) -> None:
    channel.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=json.dumps(envelope, ensure_ascii=False).encode(),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            message_id=str(envelope.get("event_id", "")),
            correlation_id=str(envelope.get("correlation_id", "")),
            headers=headers or {},
        ),
        mandatory=True,
    )
