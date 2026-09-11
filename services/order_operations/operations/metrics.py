from prometheus_client import Counter, Gauge

db_pool_exhausted = Counter(
    "operations_db_pool_exhausted_total",
    "Requests refused with 503 because no database connection became free within the pool timeout.",
)

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


command_dispatch_total = Counter(
    "operations_command_dispatch_total",
    "Command relay results.",
    # dispatched | retried | topology | expired | timed_out | invalid | superseded | dispatch_failed
    ["result"],
)

# a command sitting here means the storefront has not been told to act yet, so the age of the
# oldest pending row is the operator-facing signal for the whole command plane
command_outbox_oldest_pending_age_seconds = Gauge(
    "operations_command_outbox_oldest_pending_age_seconds",
    "Age of the oldest pending command outbox row.",
)

command_relay_connected = Gauge(
    "operations_command_relay_connected",
    "1 when the command relay holds an open channel to the storefront vhost, else 0.",
)
