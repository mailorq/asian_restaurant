import importlib
import os

import psycopg
import pytest


def test_storefront_orm_is_not_importable():
    for module in ("orders.models", "menu.models", "accounts.models"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


@pytest.mark.django_db
def test_operations_db_contains_no_storefront_tables():
    from django.db import connection

    tables = set(connection.introspection.table_names())
    assert not any(t.startswith(("orders_", "menu_", "accounts_", "cart_")) for t in tables)
    assert any(t.startswith("operations_") for t in tables)


def test_operations_credentials_cannot_reach_storefront_db():
    # DSN points at the storefront DB host but with the operations DB user/password;
    # the ops role does not exist there, so the connection must be refused.
    dsn = os.environ.get("STOREFRONT_DSN_FOR_ISOLATION")
    if not dsn:
        pytest.skip("STOREFRONT_DSN_FOR_ISOLATION not configured")
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(dsn, connect_timeout=5)
