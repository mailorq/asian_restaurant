"""RabbitMQ topology and publisher for order events.

Durable topology + publisher confirms + persistent messages give at-least-once
delivery with no broker-side loss. Paired with the OrderOutbox relay, an event
that cannot be confirmed stays pending and is retried. The ops queue dead lettrrs
poison messages to a DLQ
"""

import json

import pika
from django.conf import settings

EXCHANGE = "orders"
DLX = "orders.dlx"
OPS_QUEUE = "orders.ops"
OPS_DLQ = "orders.ops.dlq"


def connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))


def declare_topology(channel: "pika.channel.Channel") -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX, exchange_type="topic", durable=True)

    channel.queue_declare(queue=OPS_DLQ, durable=True)
    channel.queue_bind(queue=OPS_DLQ, exchange=DLX, routing_key="#")

    channel.queue_declare(
        queue=OPS_QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX}
    )
    channel.queue_bind(queue=OPS_QUEUE, exchange=EXCHANGE, routing_key="order.*")


def publish(routing_key: str, event_type: str, payload: dict, headers: dict) -> None:
    """Publish one event, waiting for a broker confirm.

    Raises (UnroutableError/NackError/connection errors) if the message is not
    confirmed, so the caller keeps the outbox row pending for retry.
    """
    conn = connect()
    try:
        channel = conn.channel()
        declare_topology(channel)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload, ensure_ascii=False).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistent
                type=event_type,
                message_id=str(headers.get("event_id", "")),
                correlation_id=str(headers.get("correlation_id", "")),
                headers=headers,
            ),
            mandatory=True,
        )
    finally:
        conn.close()
