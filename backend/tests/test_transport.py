import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone

from ops import service
from ops.management.commands.run_ops_consumer import Command as OpsConsumer
from orders import messaging
from orders.management.commands.publish_outbox import Command as Relay
from orders.management.commands.publish_outbox import _backoff_seconds
from orders.models import OrderOutbox

pytestmark = pytest.mark.django_db


def _msg(event_type="order.created", schema=1, retries=0, order_id=1):
    method = SimpleNamespace(delivery_tag=1, routing_key=event_type)
    event_id = str(uuid.uuid4())
    headers = {
        "schema_version": schema,
        "event_id": event_id,
        "correlation_id": str(uuid.uuid4()),
        "aggregate_version": 1,
        "x-retries": retries,
    }
    props = SimpleNamespace(type=event_type, message_id=event_id, headers=headers)
    body = json.dumps({"order_id": order_id, "status": "created", "items": []}).encode()
    return method, props, body


def test_bad_schema_goes_to_dlq():
    channel = Mock()
    OpsConsumer()._on_message(channel, *_msg(schema=99))
    channel.basic_nack.assert_called_once_with(1, requeue=False)
    channel.basic_ack.assert_not_called()


def test_unknown_event_type_goes_to_dlq():
    channel = Mock()
    OpsConsumer()._on_message(channel, *_msg(event_type="weird.event"))
    channel.basic_nack.assert_called_once_with(1, requeue=False)


def test_missing_order_id_goes_to_dlq():
    channel = Mock()
    method, props, _ = _msg()  # valid envelope, but body lacks order_id
    OpsConsumer()._on_message(channel, method, props, b'{"status":"created"}')
    channel.basic_nack.assert_called_once_with(1, requeue=False)


def test_missing_correlation_id_goes_to_dlq():
    channel = Mock()
    method, props, body = _msg()
    del props.headers["correlation_id"]
    OpsConsumer()._on_message(channel, method, props, body)
    channel.basic_nack.assert_called_once_with(1, requeue=False)


def test_aggregate_version_below_one_goes_to_dlq():
    channel = Mock()
    method, props, body = _msg()
    props.headers["aggregate_version"] = 0
    OpsConsumer()._on_message(channel, method, props, body)
    channel.basic_nack.assert_called_once_with(1, requeue=False)


def test_non_uuid_event_id_goes_to_dlq():
    channel = Mock()
    method, props, body = _msg()
    props.headers["event_id"] = "None"
    props.message_id = "None"
    OpsConsumer()._on_message(channel, method, props, body)
    channel.basic_nack.assert_called_once_with(1, requeue=False)


def test_malformed_retries_header_does_not_crash(monkeypatch):
    monkeypatch.setattr(service, "apply_event", lambda **k: True)
    channel = Mock()
    method, props, body = _msg()
    props.headers["x-retries"] = "not-a-number"
    OpsConsumer()._on_message(channel, method, props, body)
    channel.basic_ack.assert_called_once_with(1)


def test_out_of_order_publishes_confirmed_retry_then_acks(monkeypatch):
    monkeypatch.setattr(service, "apply_event", Mock(side_effect=service.OutOfOrder("x")))
    seen = {}
    monkeypatch.setattr(
        messaging,
        "publish_message",
        lambda ch, ex, rk, et, pl, hd: seen.update(exchange=ex, retries=hd["x-retries"]),
    )
    channel = Mock()
    OpsConsumer()._on_message(channel, *_msg(retries=0))
    assert seen == {"exchange": messaging.RETRY_EXCHANGE, "retries": 1}
    channel.basic_ack.assert_called_once_with(1)


def test_retry_publish_failure_requeues_original(monkeypatch):
    monkeypatch.setattr(service, "apply_event", Mock(side_effect=service.OutOfOrder("x")))
    monkeypatch.setattr(messaging, "publish_message", Mock(side_effect=Exception("broker down")))
    channel = Mock()
    OpsConsumer()._on_message(channel, *_msg(retries=0))
    channel.basic_nack.assert_called_once_with(1, requeue=True)  # original not lost
    channel.basic_ack.assert_not_called()


def test_exhausted_retries_go_to_dlq(monkeypatch):
    monkeypatch.setattr(service, "apply_event", Mock(side_effect=service.OutOfOrder("x")))
    channel = Mock()
    OpsConsumer()._on_message(channel, *_msg(retries=messaging.MAX_RETRIES))
    channel.basic_nack.assert_called_once_with(1, requeue=False)  # DLQ


# leased outbox relay
def _outbox(**kw):
    return OrderOutbox.objects.create(
        aggregate_id="1", event_type="order.created", routing_key="order.created", payload={"order_id": 1}, **kw
    )


def test_relay_publish_failure_backs_off_and_stays_pending(monkeypatch):
    row = _outbox(locked_by="w1", locked_until=timezone.now() + timedelta(seconds=60))
    monkeypatch.setattr(messaging, "publish", Mock(side_effect=Exception("broker down")))
    Relay()._publish_one("w1", row)
    row.refresh_from_db()
    assert row.status == OrderOutbox.Status.PENDING
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert "broker down" in row.last_error


def test_relay_success_marks_published(monkeypatch):
    row = _outbox(locked_by="w1", locked_until=timezone.now() + timedelta(seconds=60))
    monkeypatch.setattr(messaging, "publish", Mock())
    Relay()._publish_one("w1", row)
    row.refresh_from_db()
    assert row.status == OrderOutbox.Status.PUBLISHED
    assert row.published_at is not None


def test_backoff_grows_with_attempts():
    assert _backoff_seconds(5) > _backoff_seconds(1)


def test_claim_leases_rows_so_a_second_worker_skips_them():
    for _ in range(5):
        _outbox()
    relay = Relay()
    first = relay._claim("w1")
    assert len(first) == 5
    assert relay._claim("w2") == []  # all leased -> nothing left


def test_expired_lease_is_reclaimed_by_second_worker():
    row = _outbox()
    relay = Relay()
    assert [r.pk for r in relay._claim("w1")] == [row.pk]

    OrderOutbox.objects.filter(pk=row.pk).update(locked_until=timezone.now() - timedelta(seconds=1))

    assert [r.pk for r in relay._claim("w2")] == [row.pk]  # lease expired -> reclaimable
    row.refresh_from_db()
    assert row.locked_by == "w2"


def test_publish_not_committed_when_lease_expired(monkeypatch):
    # a slow worker whose lease already expired must not flip status
    row = _outbox(locked_by="w1", locked_until=timezone.now() - timedelta(seconds=1))
    monkeypatch.setattr(messaging, "publish", Mock())
    Relay()._publish_one("w1", row)
    row.refresh_from_db()
    assert row.status == OrderOutbox.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_parallel_workers_do_not_double_claim():
    for _ in range(20):
        _outbox()
    relay = Relay()

    def worker(worker_id):
        from django.db import connection

        try:
            return [row.pk for row in relay._claim(worker_id)]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(worker, "w1")
        b = pool.submit(worker, "w2")
        ids_a, ids_b = a.result(), b.result()

    assert set(ids_a).isdisjoint(ids_b)  # skip_locked -> no row claimed twice
    assert len(ids_a) + len(ids_b) <= 20
    OrderOutbox.objects.all().delete()  # transaction=True: clean up explicitly


def test_legacy_queue_is_bound_only_to_what_it_can_process():
    from unittest.mock import MagicMock

    from orders import messaging

    channel = MagicMock()
    messaging.declare_topology(channel)

    ops_binds = [
        c.kwargs["routing_key"]
        for c in channel.queue_bind.call_args_list
        if c.kwargs.get("queue") == messaging.OPS_QUEUE and c.kwargs.get("exchange") == messaging.EXCHANGE
    ]
    assert ops_binds == list(messaging.LEGACY_PROJECTION_KEYS)
    # the wildcard also matches transition outcomes, which this queue would dead-letter
    assert "order.*" not in ops_binds
    channel.queue_unbind.assert_not_called()


def test_legacy_wildcard_binding_is_converged_away():
    from unittest.mock import MagicMock

    from orders import messaging

    channel = MagicMock()
    messaging.converge_legacy_binding(channel)

    channel.queue_unbind.assert_called_once_with(
        queue=messaging.OPS_QUEUE, exchange=messaging.EXCHANGE, routing_key="order.*"
    )
