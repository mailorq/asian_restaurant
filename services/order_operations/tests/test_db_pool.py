"""
database connections under ASGI

every request thread borrows a connection from a bounded per-process pool and returns it when the
request ends. a request that cannot get one within the pool timeout is refused with a neutral 503
"""

import pytest
from django.conf import settings
from django.db import OperationalError
from django.test import Client
from prometheus_client import REGISTRY
from psycopg_pool import PoolTimeout

from operations.auth import EmployeeJWTAuth

pytestmark = pytest.mark.django_db

EXHAUSTED = "operations_db_pool_exhausted_total"


def _count():
    return REGISTRY.get_sample_value(EXHAUSTED) or 0


def _pool_timeout(*args, **kwargs):
    # the shape psycopg_pool and django produce together: django's OperationalError caused by PoolTimeout
    try:
        raise PoolTimeout("couldn't get a connection after 5.00 sec")
    except PoolTimeout as exc:
        raise OperationalError("couldn't get a connection after 5.00 sec") from exc


def _get_orders():
    return Client(raise_request_exception=False).get("/ops-api/orders", HTTP_AUTHORIZATION="Bearer token")


def test_connections_come_from_a_bounded_pool_and_are_not_kept_per_thread():
    db = settings.DATABASES["default"]
    assert db["CONN_MAX_AGE"] == 0
    pool = db["OPTIONS"]["pool"]
    assert 1 <= pool["min_size"] <= pool["max_size"]
    assert pool["timeout"] > 0


def test_an_exhausted_pool_is_a_neutral_503(monkeypatch):
    # authentication reads the authorization projection, so it is where a request first needs a connection
    monkeypatch.setattr(EmployeeJWTAuth, "authenticate", _pool_timeout)
    before = _count()

    response = _get_orders()

    assert response.status_code == 503
    assert response["Retry-After"] == "1"
    assert response.json() == {"detail": "service temporarily unavailable"}
    assert _count() == before + 1


def test_any_other_database_error_stays_a_500_without_its_text(monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(EmployeeJWTAuth, "authenticate", broken)
    before = _count()

    response = _get_orders()

    assert response.status_code == 500
    assert b"server closed" not in response.content
    assert _count() == before
