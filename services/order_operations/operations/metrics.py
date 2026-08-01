from prometheus_client import Counter

projection_events = Counter(
    "operations_projection_events_total",
    "Projection outcomes by event type and outcome.",
    ["event_type", "outcome"],
)
