"""
routing isolation between command outcomes and legacy projection traffic

the command plane has a 30s deadline, so an outcome queued behind a projection backfill turns an
applied transition into a false timed_out. these assert the two never share a queue
"""

import re

import pytest

from operations import messaging
from operations.management.commands import bridge_storefront_events as bridge

STOREFRONT_OUTCOME_KEYS = ("order.transition_succeeded", "order.transition_rejected")
STOREFRONT_LEGACY_KEYS = (
    "order.created", "order.status_changed", "inventory.stock_changed",
    "identity.customer_changed", "identity.authz_changed", "snapshot.control",
)
OPERATIONS_OUTCOME_KEYS = ("orders.transition.succeeded.v1", "orders.transition.rejected.v1")
OPERATIONS_PROJECTION_KEYS = (
    "orders.order.created.v1", "orders.order.status_changed.v1", "inventory.stock_changed.v1",
    "identity.customer_changed.v1", "identity.authz_changed.v1", "operations.snapshot.control.v1",
)


def _matches(pattern: str, key: str) -> bool:
    if pattern == "#":
        return True
    assert "#" not in pattern, f"{pattern}: multi-segment wildcards are not modelled here"
    parts = [r"[^.]+" if part == "*" else re.escape(part) for part in pattern.split(".")]
    return re.fullmatch(r"\.".join(parts), key) is not None


class RecordingChannel:
    """collects the binding table a declare pass would leave on the broker"""

    def __init__(self):
        self.bindings: set[tuple[str, str, str]] = set()
        self.unbound: set[tuple[str, str, str]] = set()
        self.consuming: list[str] = []

    def exchange_declare(self, **kwargs):
        pass

    def queue_declare(self, **kwargs):
        pass

    def queue_bind(self, *, queue, exchange, routing_key):
        self.bindings.add((exchange, queue, routing_key))

    def queue_unbind(self, *, queue, exchange, routing_key):
        self.unbound.add((exchange, queue, routing_key))
        self.bindings.discard((exchange, queue, routing_key))

    def confirm_delivery(self):
        pass

    def basic_qos(self, **kwargs):
        pass

    def basic_consume(self, *, queue, on_message_callback):
        self.consuming.append(queue)

    def start_consuming(self):
        raise KeyboardInterrupt

    def stop_consuming(self):
        pass

    def close(self):
        pass


def _delivered_to(channel, exchange, key) -> set[str]:
    return {q for ex, q, pattern in channel.bindings if ex == exchange and _matches(pattern, key)}


@pytest.fixture
def bridge_topology():
    channel = RecordingChannel()
    bridge.declare_bridge_topology(channel)
    return channel


@pytest.fixture
def operations_topology():
    channel = RecordingChannel()
    messaging.declare_topology(channel)
    return channel


def test_an_outcome_never_shares_the_bridge_queue_with_legacy_traffic(bridge_topology):
    for key in STOREFRONT_OUTCOME_KEYS:
        assert _delivered_to(bridge_topology, bridge.STOREFRONT_EXCHANGE, key) == {
            bridge.BRIDGE_OUTCOME_QUEUE
        }, key
    for key in STOREFRONT_LEGACY_KEYS:
        assert _delivered_to(bridge_topology, bridge.STOREFRONT_EXCHANGE, key) == {
            bridge.BRIDGE_QUEUE
        }, key


def test_an_outcome_never_shares_the_projection_queue(operations_topology):
    for key in OPERATIONS_OUTCOME_KEYS:
        assert _delivered_to(operations_topology, messaging.EXCHANGE, key) == {
            messaging.OUTCOME_QUEUE
        }, key
    for key in OPERATIONS_PROJECTION_KEYS:
        assert _delivered_to(operations_topology, messaging.EXCHANGE, key) == {
            messaging.QUEUE
        }, key


def test_a_retried_message_returns_to_the_queue_that_owns_its_key(bridge_topology):
    for key in STOREFRONT_OUTCOME_KEYS:
        assert _delivered_to(bridge_topology, bridge.BRIDGE_REQUEUE_EXCHANGE, key) == {
            bridge.BRIDGE_OUTCOME_QUEUE
        }, key
    for key in STOREFRONT_LEGACY_KEYS:
        assert _delivered_to(bridge_topology, bridge.BRIDGE_REQUEUE_EXCHANGE, key) == {
            bridge.BRIDGE_QUEUE
        }, key


def test_the_stale_catch_all_bindings_are_removed_from_a_running_broker(bridge_topology):
    assert (bridge.STOREFRONT_EXCHANGE, bridge.BRIDGE_QUEUE, "order.*") in bridge_topology.unbound
    assert (bridge.BRIDGE_REQUEUE_EXCHANGE, bridge.BRIDGE_QUEUE, "#") in bridge_topology.unbound


def test_the_outcome_keys_are_removed_from_the_projection_queue(operations_topology):
    for key in OPERATIONS_OUTCOME_KEYS:
        assert (messaging.EXCHANGE, messaging.QUEUE, key) in operations_topology.unbound, key


def test_the_consumer_listens_on_both_queues(monkeypatch):
    from operations.management.commands import run_operations_consumer as consumer

    channel = RecordingChannel()

    class _Connection:
        is_open = True

        def channel(self):
            return channel

        def close(self):
            pass

    monkeypatch.setattr(consumer, "start_http_server", lambda *a, **kw: None)
    monkeypatch.setattr(consumer.messaging, "connect", lambda: _Connection())

    consumer.Command().handle()

    assert set(channel.consuming) == {messaging.QUEUE, messaging.OUTCOME_QUEUE}


def test_the_bridge_listens_on_both_queues(monkeypatch):
    channel = RecordingChannel()

    class _Connection:
        is_open = True

        def channel(self):
            return channel

        def close(self):
            pass

    monkeypatch.setattr(bridge.pika, "BlockingConnection", lambda *a, **kw: _Connection())
    command = bridge.Command()
    monkeypatch.setattr(command, "_open_publish", lambda: channel)

    command.handle()

    assert set(channel.consuming) == {bridge.BRIDGE_QUEUE, bridge.BRIDGE_OUTCOME_QUEUE}


def test_every_queue_name_stays_inside_the_granted_permissions():
    for queue in (messaging.QUEUE, messaging.OUTCOME_QUEUE, messaging.DLQ, messaging.RETRY_QUEUE):
        assert queue.startswith("operations."), queue
    for queue in (bridge.BRIDGE_QUEUE, bridge.BRIDGE_OUTCOME_QUEUE, bridge.BRIDGE_DLQ,
                  bridge.BRIDGE_RETRY_QUEUE):
        assert queue.startswith("operations.bridge."), queue
