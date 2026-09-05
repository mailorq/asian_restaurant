"""
operator handling of the storefront dead-letter queues

the DLQ alerts are critical and had no matching action. replay must also stay inside the queue it
came from: `orders` feeds the operations bridge too, so a republish there would project twice
"""

import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from orders import command_messaging, messaging
from orders.management.commands import dlq as dlq_command


class FakeChannel:
    """models one queue of deliveries plus the publishes made against it"""

    def __init__(self, messages):
        self.queue = list(messages)
        self.unacked: dict[int, tuple] = {}
        self.published: list[dict] = []
        self.acked: list[int] = []
        self.publish_error = None
        self._tag = 0

    def basic_get(self, queue, auto_ack=False):
        if not self.queue:
            return None, None, None
        self._tag += 1
        routing_key, headers, body = self.queue.pop(0)
        method = SimpleNamespace(delivery_tag=self._tag, routing_key=routing_key, redelivered=False)
        properties = SimpleNamespace(
            headers=dict(headers), message_id=f"m{self._tag}", correlation_id=None,
            content_type="application/json", type="order.created",
        )
        self.unacked[self._tag] = (routing_key, headers, body)
        return method, properties, body

    def basic_publish(self, exchange, routing_key, body, properties=None, mandatory=False):
        if self.publish_error:
            raise self.publish_error
        self.published.append({
            "exchange": exchange, "routing_key": routing_key,
            "headers": dict((properties.headers or {}) if properties else {}),
        })

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)
        self.unacked.pop(delivery_tag, None)

    def basic_nack(self, delivery_tag, requeue=False):
        if requeue:
            self.queue.append(self.unacked.pop(delivery_tag))
        else:
            self.unacked.pop(delivery_tag, None)

    def confirm_delivery(self):
        pass

    def close(self):
        pass


def _messages(count=3, key="order.created"):
    return [
        (key, {"x-retries": 5, "x-death": [{"reason": "rejected"}]},
         json.dumps({"event_type": key, "n": i}).encode())
        for i in range(count)
    ]


@pytest.fixture
def channel(monkeypatch):
    chan = FakeChannel(_messages())
    monkeypatch.setattr(
        dlq_command.messaging, "connect",
        lambda: SimpleNamespace(channel=lambda: chan, close=lambda: None, is_open=True),
    )
    return chan


def test_listing_leaves_every_message_in_place(channel, capsys):
    call_command("dlq", messaging.OPS_DLQ, "--list")

    assert len(channel.queue) == 3
    assert channel.acked == []
    assert "order.created" in capsys.readouterr().out


def test_replay_goes_to_the_owning_queue_not_through_the_exchange(channel):
    call_command("dlq", messaging.OPS_DLQ, "--replay", "2")

    assert [p["exchange"] for p in channel.published] == ["", ""], (
        "republishing to the orders exchange would also reach the operations bridge"
    )
    assert [p["routing_key"] for p in channel.published] == [messaging.OPS_QUEUE] * 2
    assert len(channel.acked) == 2


def test_the_command_queue_replays_into_its_own_queue(channel):
    call_command("dlq", command_messaging.DLQ, "--replay", "1")

    assert channel.published[0]["routing_key"] == command_messaging.QUEUE


def test_replay_clears_the_spent_retry_budget_and_records_who_did_it(channel):
    call_command("dlq", messaging.OPS_DLQ, "--replay", "1", "--operator", "ops-7")

    headers = channel.published[0]["headers"]
    assert "x-retries" not in headers and "x-death" not in headers
    assert headers["x-replayed-by"] == "ops-7"
    assert headers["x-replayed-at"]


def test_a_message_is_never_acked_before_its_publish_is_confirmed(channel):
    channel.publish_error = RuntimeError("broker refused")

    with pytest.raises(CommandError):
        call_command("dlq", messaging.OPS_DLQ, "--replay", "3")

    assert channel.acked == []
    assert len(channel.queue) == 3, "the message must stay in the dead-letter queue"


def test_replay_stops_at_the_requested_count(channel):
    call_command("dlq", messaging.OPS_DLQ, "--replay", "1")

    assert len(channel.published) == 1 and len(channel.queue) == 2


def test_an_empty_queue_is_not_an_error(monkeypatch):
    chan = FakeChannel([])
    monkeypatch.setattr(
        dlq_command.messaging, "connect",
        lambda: SimpleNamespace(channel=lambda: chan, close=lambda: None, is_open=True),
    )

    call_command("dlq", messaging.OPS_DLQ, "--replay", "5")

    assert chan.published == []


def test_dropping_needs_an_explicit_confirmation_and_a_reason(channel):
    with pytest.raises(CommandError):
        call_command("dlq", messaging.OPS_DLQ, "--drop", "1")
    with pytest.raises(CommandError):
        call_command("dlq", messaging.OPS_DLQ, "--drop", "1", "--yes")

    assert len(channel.queue) == 3, "nothing may be discarded without both"


def test_a_confirmed_drop_discards_exactly_the_requested_count(channel, caplog):
    call_command("dlq", messaging.OPS_DLQ, "--drop", "2", "--yes", "--reason", "unprocessable")

    assert len(channel.acked) == 2 and len(channel.queue) == 1
    assert channel.published == []
    assert any("dlq message discarded" in r.message for r in caplog.records)


def test_an_unknown_queue_is_refused(channel):
    with pytest.raises(CommandError):
        call_command("dlq", "orders.ops", "--list")

    assert len(channel.queue) == 3


def test_replay_and_drop_are_mutually_exclusive(channel):
    with pytest.raises(CommandError):
        call_command("dlq", messaging.OPS_DLQ, "--replay", "1", "--drop", "1", "--yes", "--reason", "x")

    assert len(channel.queue) == 3
