"""
command topology on the storefront vhost

the storefront consumer is the sole owner of this topology. the operations publisher holds
`configure=^$`, so it can neither declare nor repair any of it and must find it already there
"""

EXCHANGE = "commands"
QUEUE = "commands.orders"
DLX = "commands.dlx"
DLQ = "commands.orders.dlq"
RETRY_EXCHANGE = "commands.retry"
RETRY_QUEUE = "commands.orders.retry"
RETRY_TTL_MS = 5000
MAX_RETRIES = 5

REQUESTED_ROUTING_KEY = "orders.transition.requested"


def declare_topology(channel) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=RETRY_EXCHANGE, exchange_type="topic", durable=True)

    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_bind(queue=DLQ, exchange=DLX, routing_key="#")

    # delayed retry: messages sit for RETRY_TTL_MS then dead-letter back to the main exchange
    channel.queue_declare(
        queue=RETRY_QUEUE,
        durable=True,
        arguments={"x-message-ttl": RETRY_TTL_MS, "x-dead-letter-exchange": EXCHANGE},
    )
    channel.queue_bind(queue=RETRY_QUEUE, exchange=RETRY_EXCHANGE, routing_key="orders.transition.*")

    channel.queue_declare(queue=QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX})
    channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=REQUESTED_ROUTING_KEY)
