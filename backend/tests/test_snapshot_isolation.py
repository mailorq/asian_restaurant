from decimal import Decimal

import psycopg
import pytest
from django.db import connection, transaction

from menu.models import Product

_INSERT = (
    "INSERT INTO menu_product "
    "(code, category, name, description, allergens, price, image, stock_quantity, version, is_active, is_featured, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())"
)


def _second_connection_dsn() -> str:
    sd = connection.settings_dict
    return (f"host={sd['HOST']} port={sd['PORT'] or 5432} dbname={sd['NAME']} "
            f"user={sd['USER']} password={sd['PASSWORD']}")


@pytest.mark.django_db(transaction=True)
def test_snapshot_repeatable_read_excludes_post_boundary_insert():
    # proves the isolation emit_source_state --snapshot relies on: a row committed by another
    # connection after the source boundary is invisible to the snapshot scan
    Product.objects.create(code="p1", category="dish", name="p1", price=Decimal("1.00"), stock_quantity=1)

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        before = Product.objects.count()  # first read establishes the snapshot boundary
        with psycopg.connect(_second_connection_dsn(), autocommit=True) as conn2:
            conn2.execute(_INSERT, ("p2", "dish", "p2", "", "", 1, "", 1, 1, True, False))
        after = Product.objects.count()
        assert before == 1 and after == 1  # the concurrent insert stays out of the snapshot
    assert Product.objects.count() == 2  # visible only once the snapshot transaction ends
