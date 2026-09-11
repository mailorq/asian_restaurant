"""
database connections under ASGI

every request thread borrows a connection from a bounded per-process pool and returns it when the
request ends. a request that cannot get one within the pool timeout is refused with a neutral 503
"""

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.db import OperationalError
from django.test import Client
from prometheus_client import REGISTRY
from psycopg_pool import PoolTimeout

from operations import auth
from operations.models import EmployeeAuthorization

pytestmark = pytest.mark.django_db

EXHAUSTED = "operations_db_pool_exhausted_total"


@pytest.fixture
def keypair(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "_signing_key", lambda token: key.public_key())
    return key


def _count():
    return REGISTRY.get_sample_value(EXHAUSTED) or 0


def _get_orders(key, sub="7"):
    now = int(time.time())
    token = pyjwt.encode({"iss": "identity", "aud": "operations", "sub": sub, "roles": ["restaurant_employee"],
                          "authz_version": 1, "jti": "x", "iat": now, "exp": now + 600}, key, algorithm="RS256")
    return Client(raise_request_exception=False).get("/ops-api/orders", HTTP_AUTHORIZATION=f"Bearer {token}")


def _projection_raises(monkeypatch, exc):
    # authentication reads the authorization projection, so it is where a request first needs a connection
    def query(*args, **kwargs):
        raise exc()

    monkeypatch.setattr(EmployeeAuthorization.objects, "filter", query)


def _pool_timeout():
    # the shape psycopg_pool and django produce together: django's OperationalError caused by PoolTimeout
    error = OperationalError("couldn't get a connection after 5.00 sec")
    error.__cause__ = PoolTimeout("couldn't get a connection after 5.00 sec")
    return error


def test_connections_come_from_a_bounded_pool_and_are_not_kept_per_thread():
    db = settings.DATABASES["default"]
    assert db["CONN_MAX_AGE"] == 0
    pool = db["OPTIONS"]["pool"]
    assert 1 <= pool["min_size"] <= pool["max_size"]
    assert pool["timeout"] > 0


def test_an_exhausted_pool_during_authentication_is_a_neutral_503(keypair, monkeypatch):
    _projection_raises(monkeypatch, _pool_timeout)
    before = _count()

    response = _get_orders(keypair)

    assert response.status_code == 503
    assert response["Retry-After"] == "1"
    assert response.json() == {"detail": "service temporarily unavailable"}
    assert _count() == before + 1


def test_an_unreadable_projection_is_a_500_without_its_text_and_grants_nothing(keypair, monkeypatch):
    _projection_raises(monkeypatch, lambda: OperationalError("server closed the connection unexpectedly"))
    before = _count()

    response = _get_orders(keypair)

    assert response.status_code == 500
    assert b"server closed" not in response.content
    assert _count() == before


@pytest.mark.parametrize("sub", ["not-a-number", str(2**40), "-1"])
def test_a_subject_the_projection_cannot_hold_is_rejected_not_failed(keypair, sub):
    assert _get_orders(keypair, sub=sub).status_code == 401
