"""business metrics. registered on the shared prometheus_client registry and
served at /metrics alongside django-prometheus infra/perf series."""

from prometheus_client import Counter, Gauge, Histogram

orders_created_total = Counter(
    "orders_created_total",
    "Orders successfully placed.",
    ["payment_method"],
)

order_value_hryvnia = Histogram(
    "order_value_hryvnia",
    "Order total amount in UAH.",
    buckets=(100, 200, 300, 500, 750, 1000, 1500, 2500, 5000),
)

order_items_per_order = Histogram(
    "order_items_per_order",
    "Distinct line items per order.",
    buckets=(1, 2, 3, 5, 8, 13, 21),
)

order_create_failures_total = Counter(
    "order_create_failures_total",
    "Rejected order attempts, by reason.",
    ["reason"],  # validation | product_unavailable | unauthenticated
)

user_registrations_total = Counter(
    "user_registrations_total",
    "Completed user registrations.",
)

login_attempts_total = Counter(
    "login_attempts_total",
    "Login attempts, by outcome.",
    ["result"],  # success | invalid_credentials | rate_limited
)

db_pool_exhausted_total = Counter(
    "db_pool_exhausted_total",
    "Requests refused with 503 because no database connection became free within the pool timeout.",
)

catalog_cache_events_total = Counter(
    "catalog_cache_events_total",
    "Menu catalog cache lookups.",
    ["event"],  # hit | miss
)


# readiness for the command consumer: 1 only while it holds a connection with the command
# topology declared and is consuming. a live /metrics alone does not prove it applies commands
commands_consumer_connected = Gauge(
    "commands_consumer_connected",
    "1 when the command consumer is connected with its topology declared, else 0.",
)

commands_applied_total = Counter(
    "commands_applied_total",
    "Transition commands applied, by outcome.",
    ["outcome"],  # succeeded | rejected | replayed
)
