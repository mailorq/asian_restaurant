"""wire-level checks of the command transport against a real broker

skipped unless COMMANDS_MQ_URL_FOR_TRANSPORT is set; these assert routing and delivery rather
than application logic, which the fake-channel tests already cover

destructive: purges commands.orders, and it reads that queue directly, so point it only at a
throwaway broker with no command consumer attached
"""

import datetime as dt
import json
import os
import time
import uuid

import pika
import pytest
from event_contracts import OrderTransitionRequestedData, parse_event
from pika.exceptions import AMQPConnectionError, UnroutableError

from orders import command_messaging as topology
from orders.management.commands.consume_commands import Command as ConsumerCommand
from orders.models import CommandInbox, Order, OrderOutbox

URL = os.environ.get("COMMANDS_MQ_URL_FOR_TRANSPORT")

if os.environ.get("REQUIRE_COMMAND_TRANSPORT_TESTS") == "1" and not URL:
    raise RuntimeError(
        "REQUIRE_COMMAND_TRANSPORT_TESTS is set but COMMANDS_MQ_URL_FOR_TRANSPORT is missing"
    )

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(not URL, reason="COMMANDS_MQ_URL_FOR_TRANSPORT not configured"),
]

CONNECT_TIMEOUT_SECONDS = 60


def _connect():
    deadline = time.monotonic() + CONNECT_TIMEOUT_SECONDS
    while True:
        try:
            return pika.BlockingConnection(pika.URLParameters(URL))
        except AMQPConnectionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


@pytest.fixture
def channel():
    connection = _connect()
    chan = connection.channel()
    topology.declare_topology(chan)
    chan.confirm_delivery()
    for queue in (topology.QUEUE, topology.DLQ, topology.RETRY_QUEUE):
        chan.queue_purge(queue)
    yield chan
    if connection.is_open:
        connection.close()


def _ready(queue) -> int:
    connection = _connect()
    try:
        return connection.channel().queue_declare(queue=queue, passive=True).method.message_count
    finally:
        connection.close()


def _settled(channel) -> dict[str, int]:
    # closing requeues whatever is still unacknowledged, so these counts see the ack
    channel.close()
    return {q: _ready(q) for q in (topology.QUEUE, topology.DLQ, topology.RETRY_QUEUE)}


@pytest.fixture
def order(user, make_product, seed_cart):
    from orders import service as order_service

    product = make_product(price="100.00", stock=10)
    seed_cart(user.id, {product.id: 2}, version=1)
    return order_service.checkout(user, "ул. Пушкина, 12", "cash", f"idem-{uuid.uuid4().hex[:8]}")


def _envelope(actor, order_id, *, command_id=None):
    data = OrderTransitionRequestedData(
        command_id=command_id or uuid.uuid4(),
        actor_id=actor.id,
        actor_authz_version=actor.authz_version,
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=30),
        order_id=order_id,
        expected_status="created",
        target_status="confirmed",
        reason="",
    )
    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": "orders.transition.requested.v1",
        "schema_version": 1,
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "producer": "operations",
        "aggregate": {"type": "order", "id": str(order_id), "version": 1},
        "correlation_id": str(uuid.uuid4()),
        "causation_id": None,
        "data": json.loads(data.model_dump_json()),
    }
    parse_event(envelope)
    return envelope


def _publish(channel, envelope, routing_key=topology.REQUESTED_ROUTING_KEY):
    channel.basic_publish(
        exchange=topology.EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(envelope).encode(),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        mandatory=True,
    )


def _consume_one(channel):
    method, properties, body = channel.basic_get(queue=topology.QUEUE, auto_ack=False)
    assert method is not None, (
        f"nothing to read from {topology.QUEUE}: the message was routed, so another consumer "
        "is attached to this broker"
    )
    ConsumerCommand()._on_message(channel, method, properties, body)
    return method


def test_published_command_reaches_the_consumer_and_moves_the_order(channel, order, employee_user):
    _publish(channel, _envelope(employee_user, order.id))

    _consume_one(channel)

    assert Order.objects.get(pk=order.pk).status == "confirmed"
    assert OrderOutbox.objects.filter(event_type="orders.transition.succeeded.v1").count() == 1
    assert _settled(channel) == {topology.QUEUE: 0, topology.DLQ: 0, topology.RETRY_QUEUE: 0}


def test_redelivery_over_the_wire_applies_the_command_once(channel, order, employee_user):
    envelope = _envelope(employee_user, order.id)
    _publish(channel, envelope)
    _publish(channel, envelope)

    _consume_one(channel)
    _consume_one(channel)

    assert CommandInbox.objects.count() == 1
    assert OrderOutbox.objects.filter(event_type="orders.transition.succeeded.v1").count() == 1
    assert _settled(channel) == {topology.QUEUE: 0, topology.DLQ: 0, topology.RETRY_QUEUE: 0}


def test_command_queue_accepts_only_the_request_routing_key(channel, order, employee_user):
    with pytest.raises(UnroutableError):
        _publish(channel, _envelope(employee_user, order.id), routing_key="orders.transition.succeeded")
