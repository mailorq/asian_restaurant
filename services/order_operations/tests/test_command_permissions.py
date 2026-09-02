"""
least-privilege checks for the command publisher credential

skipped unless COMMANDS_MQ_URL_FOR_PERMISSIONS points at a provisioned broker, because these
assert broker-side authorisation rather than application behaviour
"""

import os

import pika
import pytest
from pika.exceptions import ChannelClosedByBroker

URL = os.environ.get("COMMANDS_MQ_URL_FOR_PERMISSIONS")
ADMIN_URL = os.environ.get("ADMIN_MQ_URL_FOR_PERMISSIONS")

pytestmark = pytest.mark.skipif(
    not URL or not ADMIN_URL, reason="COMMANDS_MQ_URL_FOR_PERMISSIONS not configured"
)

EXCHANGE = "commands"
ALLOWED_KEY = "orders.transition.requested"


@pytest.fixture
def publisher():
    conn = pika.BlockingConnection(pika.URLParameters(URL))
    yield conn
    if conn.is_open:
        conn.close()


def _channel(conn):
    channel = conn.channel()
    channel.confirm_delivery()
    return channel


def _publish(channel, routing_key, exchange=EXCHANGE):
    channel.basic_publish(
        exchange=exchange, routing_key=routing_key, body=b"{}",
        properties=pika.BasicProperties(delivery_mode=2),
        mandatory=False,
    )


def test_publisher_may_send_on_the_agreed_routing_key(publisher):
    _publish(_channel(publisher), ALLOWED_KEY)


def test_publisher_cannot_use_another_routing_key(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _publish(_channel(publisher), "orders.transition.succeeded")
    assert exc.value.reply_code == 403


def test_publisher_cannot_declare_an_exchange(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _channel(publisher).exchange_declare(exchange="commands.rogue", exchange_type="topic", durable=True)
    assert exc.value.reply_code == 403


def test_publisher_cannot_declare_a_queue(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _channel(publisher).queue_declare(queue="commands.rogue", durable=True)
    assert exc.value.reply_code == 403


def test_publisher_cannot_redeclare_the_command_exchange(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _channel(publisher).exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    assert exc.value.reply_code == 403


def test_publisher_cannot_consume_the_command_queue(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _channel(publisher).basic_get(queue="commands.orders")
    assert exc.value.reply_code == 403


def test_publisher_cannot_publish_to_another_exchange(publisher):
    with pytest.raises(ChannelClosedByBroker) as exc:
        _publish(_channel(publisher), "order.created", exchange="orders")
    assert exc.value.reply_code == 403
