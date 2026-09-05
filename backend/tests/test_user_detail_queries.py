"""
query cost of the employee user card

the card nests every order of the user, so a resolver that walks each one would make the cost
grow with that history. it is flat today and this pins it there
"""

import uuid

import pytest

from orders.models import DeliveryAddress, Order

pytestmark = pytest.mark.django_db

PATH = "/api/employee/users"


def _orders(owner, count):
    address = DeliveryAddress.objects.create(user=owner, address="ул. Тестовая, 1")
    for _ in range(count):
        Order.objects.create(
            user=owner, status="created", total="10.00", phone="+79990000001",
            delivery_address=address, idempotency_key=uuid.uuid4().hex,
            source_cart_id=uuid.uuid4().hex, source_cart_version=1,
        )


def _queries_for(api, user_id) -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as captured:
        assert api.get(f"{PATH}/{user_id}").status_code == 200
    return len(captured)


def test_the_card_costs_the_same_whether_the_user_has_two_orders_or_twenty(
    api, employee_user, user, django_user_model
):
    other = django_user_model.objects.create_user(username="+79990000098", password="Pass!2345")
    _orders(user, 2)
    _orders(other, 20)
    api.force_login(employee_user)

    small = _queries_for(api, user.id)
    large = _queries_for(api, other.id)

    assert large == small, f"{small} queries for 2 orders, {large} for 20: the card scales with history"


def test_the_card_still_lists_every_order_of_that_user(api, employee_user, user):
    _orders(user, 3)
    api.force_login(employee_user)

    body = api.get(f"{PATH}/{user.id}").json()

    assert len(body["orders"]) == 3
    assert body["id"] == user.id
