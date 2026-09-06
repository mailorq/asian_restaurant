"""what an operator tool may write down

a dead-lettered order event carries a phone number and an address. the tool has to be usable
without shipping those into whatever collects the logs
"""

import hashlib
import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from operations.management.commands import dlq as dlq_command
from tests.test_dlq_tool import FakeChannel

PHONE = "+79990001111"
ADDRESS = "ул. Пушкина, 12, кв. 5"
BODY = json.dumps({"event_type": "orders.order.created.v1",
                   "data": {"phone": PHONE, "address": ADDRESS}}).encode()

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(monkeypatch):
    chan = FakeChannel([("orders.order.created.v1", {"x-death": [{"reason": "rejected"}]}, BODY)])
    monkeypatch.setattr(
        dlq_command.messaging, "connect",
        lambda: SimpleNamespace(channel=lambda: chan, close=lambda: None, is_open=True),
    )
    return chan


def test_listing_does_not_print_the_payload(channel, capsys):
    call_command("dlq", "--list")

    out = capsys.readouterr().out
    assert PHONE not in out and ADDRESS not in out
    assert hashlib.sha256(BODY).hexdigest()[:16] in out


def test_the_payload_is_available_behind_an_explicit_flag(channel, capsys):
    call_command("dlq", "--list", "--show-payload")

    assert PHONE in capsys.readouterr().out


def test_discarding_records_a_hash_not_the_payload(channel, caplog):
    call_command("dlq", "--drop", "1", "--yes", "--reason", "unprocessable")

    record = next(r for r in caplog.records if "discarded" in r.message)
    assert PHONE not in json.dumps(record.__dict__, default=str)
    assert getattr(record, "body_sha256", "").startswith(hashlib.sha256(BODY).hexdigest()[:16])
