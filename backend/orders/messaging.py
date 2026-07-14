"""RabbitMQ publisher for order events.

Durable topology + publisher confirms + persistent messages give at-least-once
delivery with no broker-side loss. Paired with the OrderOutbox relay, an event
that cannot be confirmed stays pending and is retried.
"""

import json

import pika
from django.conf import settings

EXCHANGE = "orders"
QUEUE = "orders.created"
ROUTING_KEY = "order.created"


def _connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))


def declare_topology(channel: "pika.channel.Channel") -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY)


def publish(event_type: str, payload: dict) -> None:
    """Publish one event, waiting for a broker confirm.

    Raises (UnroutableError/NackError/connection errors) if the message is not
    confirmed, so the caller keeps the outbox row pending for retry.
    """
    conn = _connect()
    try:
        channel = conn.channel()
        declare_topology(channel)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=ROUTING_KEY,
            body=json.dumps(payload, ensure_ascii=False).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistent
                type=event_type,
            ),
            mandatory=True,
        )
    finally:
        conn.close()
