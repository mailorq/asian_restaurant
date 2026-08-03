from prometheus_client import Counter, Gauge

projection_events = Counter(
    "operations_projection_events_total",
    "Projection outcomes by event type and outcome.",
    ["event_type", "outcome"],
)

# readiness: 1 only while connected to RabbitMQ with topology declared, else 0.
# A /metrics 200 alone does not prove the consumer is actually consuming.
consumer_connected = Gauge(
    "operations_consumer_connected",
    "1 when the consumer is connected to RabbitMQ with topology declared, else 0.",
)

