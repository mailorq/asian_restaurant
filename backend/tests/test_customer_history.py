"""bounded customer order history

the user card resolved every order the customer had ever placed, so the response grew with the
history. the card now shows a fixed preview and a count; the full list is its own paged endpoint
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.roles import StaffRole
from orders.models import ACTIVE_ORDER_STATUSES, DeliveryAddress, Order

pytestmark = pytest.mark.django_db

PREVIEW = 5
MAX_PAGE = 50


def _staff(username, role):
    user = get_user_model().objects.create_user(username=username, password="Pass!2345")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


@pytest.fixture
def operator():
    return _staff("+79990000401", StaffRole.OPERATOR)


@pytest.fixture
def manager():
    return _staff("+79990000402", StaffRole.MANAGER)


def _orders(owner, count, status="created"):
    address = DeliveryAddress.objects.create(user=owner, address="ул. Тестовая, 1")
    return [
        Order.objects.create(
            user=owner, status=status, total="10.00", phone="+79990000001",
            delivery_address=address, idempotency_key=uuid.uuid4().hex,
            source_cart_id=uuid.uuid4().hex, source_cart_version=1,
        )
        for _ in range(count)
    ]


def _detail(api, user_id):
    return api.get(f"/api/employee/users/{user_id}")


def _history(api, user_id, query=""):
    return api.get(f"/api/employee/users/{user_id}/orders{query}")


def test_the_card_shows_a_fixed_preview_and_the_real_total(api, manager, user):
    _orders(user, 12)
    api.force_login(manager)

    body = _detail(api, user.id).json()

    assert body["orders_total"] == 12
    assert len(body["orders_preview"]) == PREVIEW
    assert "orders" not in body, "the unbounded field must be gone, not merely shortened"


def test_the_card_costs_the_same_whatever_the_history(api, manager, user, django_user_model):
    other = django_user_model.objects.create_user(username="+79990000403", password="Pass!2345")
    _orders(user, 2)
    _orders(other, 60)
    api.force_login(manager)

    def cost(user_id):
        with CaptureQueriesContext(connection) as captured:
            assert _detail(api, user_id).status_code == 200
        return len(captured)

    assert cost(user.id) == cost(other.id)


def test_the_preview_is_newest_first(api, manager, user):
    made = _orders(user, 8)
    api.force_login(manager)

    ids = [o["id"] for o in _detail(api, user.id).json()["orders_preview"]]

    assert ids == sorted((o.id for o in made), reverse=True)[:PREVIEW]


def test_the_history_endpoint_is_paged_and_capped(api, manager, user):
    _orders(user, 70)
    api.force_login(manager)

    body = _history(api, user.id, "?page=1&page_size=1000").json()

    assert body["total"] == 70
    assert len(body["items"]) == MAX_PAGE
    assert body["page_size"] == MAX_PAGE


def test_the_history_pages_without_gaps_or_repeats(api, manager, user):
    _orders(user, 25)
    api.force_login(manager)

    seen = []
    for page in (1, 2, 3):
        seen.extend(o["id"] for o in _history(api, user.id, f"?page={page}&page_size=10").json()["items"])

    assert len(seen) == 25 and len(set(seen)) == 25


def test_orders_sharing_a_timestamp_still_page_in_a_stable_order(api, manager, user):
    from django.utils import timezone

    made = _orders(user, 6)
    Order.objects.filter(pk__in=[o.pk for o in made]).update(created_at=timezone.now())
    api.force_login(manager)

    seen = []
    for page in (1, 2, 3):
        seen.extend(o["id"] for o in _history(api, user.id, f"?page={page}&page_size=2").json()["items"])

    assert seen == sorted(seen, reverse=True)
    assert len(set(seen)) == 6


@pytest.mark.parametrize("scope,expected", [("active", 3), ("history", 2), ("all", 5)])
def test_the_scope_filter_selects_what_it_names(api, manager, user, scope, expected):
    _orders(user, 3, status=sorted(ACTIVE_ORDER_STATUSES)[0])
    _orders(user, 2, status="delivered")
    api.force_login(manager)

    assert _history(api, user.id, f"?scope={scope}").json()["total"] == expected


def test_ascending_order_is_available_and_deterministic(api, manager, user):
    made = _orders(user, 6)
    api.force_login(manager)

    ids = [o["id"] for o in _history(api, user.id, "?sort=created_at_asc").json()["items"]]

    assert ids == sorted(o.id for o in made)


@pytest.mark.parametrize("query", ["?sort=total", "?sort=id;drop", "?scope=everything"])
def test_an_unknown_filter_or_sort_is_refused(api, manager, user, query):
    api.force_login(manager)

    assert _history(api, user.id, query).status_code == 422


def test_an_operator_cannot_read_customer_history(api, operator, user):
    _orders(user, 3)
    api.force_login(operator)

    assert _history(api, user.id).status_code == 403


def test_a_customer_cannot_read_any_history(api, user):
    api.force_login(user)

    assert _history(api, user.id).status_code == 403


def test_an_unknown_customer_is_not_found(api, manager):
    api.force_login(manager)

    assert _history(api, 999999).status_code == 404


def test_the_history_costs_the_same_whatever_the_page_holds(api, manager, user, django_user_model):
    other = django_user_model.objects.create_user(username="+79990000404", password="Pass!2345")
    _orders(user, 3)
    _orders(other, 60)
    api.force_login(manager)

    def cost(user_id, size):
        with CaptureQueriesContext(connection) as captured:
            assert _history(api, user_id, f"?page=1&page_size={size}").status_code == 200
        return len(captured)

    assert cost(user.id, 3) == cost(other.id, 50)
