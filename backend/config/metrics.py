"""business metrics. registered on the shared prometheus_client registry and
served at /metrics alongside django-prometheus infra/perf series."""

from prometheus_client import Counter, Histogram

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

catalog_cache_events_total = Counter(
    "catalog_cache_events_total",
    "Menu catalog cache lookups.",
    ["event"],  # hit | miss
)
