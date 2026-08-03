import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from event_contracts import EVENT_ORDER_CREATED

from operations.management.commands.bridge_storefront_events import (
    BRIDGE_MAX_RETRIES,
    BRIDGE_RETRY_EXCHANGE,
    ORIGIN_PRODUCER,
    RELAYED_BY,
    RETRY_HEADER,
    Command,
    _map_data,
    build_envelope,
)

OCCURRED_AT = "2026-08-01T10:30:00+00:00"


def _legacy(headers_extra=None, drop_product_code=False):
    item = {
        "product_id": 3,
        "product_code": "dish_3",
        "name": "Рамен",
        "quantity": 3,
        "unit_price": "19.99",
        "line_total": "59.97",
    }
    if drop_product_code:
        del item["product_code"]
    body = json.dumps(
        {
            "order_id": 42,
            "user_id": 7,
            "status": "created",
            "total": "59.97",
            "recipient_name": "Иван",
            "items": [item],
        }
    ).encode()
    headers = {
        "event_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "aggregate_version": 1,
        "occurred_at": OCCURRED_AT,
    }
    if headers_extra:
        headers.update(headers_extra)
    props = SimpleNamespace(
        type="order.created",
        message_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        content_type="application/json",
        headers=headers,
    )
    method = SimpleNamespace(delivery_tag=1, routing_key="order.created")
    return props, method, body


def _legacy_stock(snapshot=False):
    body = json.dumps({"product_code": "dish_3", "name": "Рамен", "stock_quantity": 12}).encode()
    headers = {"event_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4()),
               "aggregate_version": 4, "occurred_at": OCCURRED_AT, "snapshot": snapshot}
    props = SimpleNamespace(type="inventory.stock_changed", message_id=str(uuid.uuid4()),
                            correlation_id=str(uuid.uuid4()), content_type="application/json", headers=headers)
    method = SimpleNamespace(delivery_tag=1, routing_key="inventory.stock_changed")
    return props, method, body


def _cmd(publish_side_effect=None):
    cmd = Command()
    cmd.publish_channel = MagicMock()
    if publish_side_effect is not None:
        cmd.publish_channel.basic_publish.side_effect = publish_side_effect
    return cmd


def test_stock_event_maps_to_product_aggregate():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy_stock()

    cmd._on_message(ch, method, props, body)

    _, kwargs = cmd.publish_channel.basic_publish.call_args
    env = json.loads(kwargs["body"])
    assert env["aggregate"] == {"type": "product", "id": "dish_3", "version": 4}
    assert env["data"]["stock_quantity"] == 12
    assert env["snapshot"] is False
    ch.basic_ack.assert_called_once_with(method.delivery_tag)


def test_snapshot_flag_is_propagated():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy_stock(snapshot=True)

    cmd._on_message(ch, method, props, body)

    _, kwargs = cmd.publish_channel.basic_publish.call_args
    assert json.loads(kwargs["body"])["snapshot"] is True


def test_valid_created_is_published_and_acked():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy()

    cmd._on_message(ch, method, props, body)

    cmd.publish_channel.basic_publish.assert_called_once()
    _, kwargs = cmd.publish_channel.basic_publish.call_args
    published = json.loads(kwargs["body"])
    item = published["data"]["items"][0]
    assert item["product_code"] == "dish_3"
    assert item["source_product_id"] == 3
    assert item["line_total"] == "59.97"
    ch.basic_ack.assert_called_once_with(method.delivery_tag)
    ch.basic_nack.assert_not_called()


def test_unknown_legacy_type_goes_to_dlq():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy()
    props.type = "order.deleted"

    cmd._on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(method.delivery_tag, requeue=False)
    cmd.publish_channel.basic_publish.assert_not_called()


def test_invalid_json_goes_to_dlq():
    cmd = _cmd()
    ch = MagicMock()
    props, method, _ = _legacy()

    cmd._on_message(ch, method, props, b"{not json")

    ch.basic_nack.assert_called_once_with(method.delivery_tag, requeue=False)
    cmd.publish_channel.basic_publish.assert_not_called()


def test_contract_violation_is_poison_not_retried():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy(drop_product_code=True)

    cmd._on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(method.delivery_tag, requeue=False)
    cmd.publish_channel.basic_publish.assert_not_called()


def test_missing_occurred_at_goes_to_dlq():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy()
    del props.headers["occurred_at"]

    cmd._on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(method.delivery_tag, requeue=False)
    cmd.publish_channel.basic_publish.assert_not_called()


def test_publish_failure_is_retried():
    cmd = _cmd(publish_side_effect=Exception("broker down"))
    ch = MagicMock()
    props, method, body = _legacy()

    cmd._on_message(ch, method, props, body)

    ch.basic_publish.assert_called_once()
    _, kwargs = ch.basic_publish.call_args
    assert kwargs["exchange"] == BRIDGE_RETRY_EXCHANGE
    assert kwargs["properties"].headers[RETRY_HEADER] == 1
    assert kwargs["properties"].type == "order.created"
    ch.basic_ack.assert_called_once_with(method.delivery_tag)
    ch.basic_nack.assert_not_called()


def test_exhausted_retries_go_to_dlq():
    cmd = _cmd(publish_side_effect=Exception("still down"))
    ch = MagicMock()
    props, method, body = _legacy({RETRY_HEADER: BRIDGE_MAX_RETRIES})

    cmd._on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(method.delivery_tag, requeue=False)
    ch.basic_publish.assert_not_called()


def test_map_data_uses_real_code_and_decimal():
    legacy = {
        "order_id": 1,
        "user_id": 2,
        "status": "created",
        "total": "59.97",
        "items": [
            {"product_id": 3, "product_code": "dish_3", "name": "x", "quantity": 3, "unit_price": "19.99", "line_total": "59.97"}
        ],
    }
    item = _map_data(EVENT_ORDER_CREATED, legacy)["items"][0]
    assert item["product_code"] == "dish_3"
    assert item["product_code"] != str(item["source_product_id"])
    assert item["source_product_id"] == 3
    assert item["line_total"] == "59.97"


def test_map_data_line_total_fallback_uses_decimal():
    legacy = {
        "order_id": 1,
        "items": [{"product_id": 3, "product_code": "dish_3", "quantity": 3, "unit_price": "19.99"}],
    }
    item = _map_data(EVENT_ORDER_CREATED, legacy)["items"][0]
    assert item["line_total"] == "59.97"


def test_envelope_preserves_origin_time_and_provenance():
    props, _method, body = _legacy()
    legacy = json.loads(body)
    envelope = build_envelope(props, EVENT_ORDER_CREATED, legacy)
    assert envelope["occurred_at"] == OCCURRED_AT
    assert envelope["producer"] == ORIGIN_PRODUCER == "storefront"
    assert envelope["relayed_by"] == RELAYED_BY

    published = _publish_and_get_envelope()
    assert published["occurred_at"] == OCCURRED_AT
    assert published["producer"] == "storefront"


def _publish_and_get_envelope():
    cmd = _cmd()
    ch = MagicMock()
    props, method, body = _legacy()
    cmd._on_message(ch, method, props, body)
    _, kwargs = cmd.publish_channel.basic_publish.call_args
    return json.loads(kwargs["body"])
