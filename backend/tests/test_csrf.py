import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _client(user):
    c = Client(enforce_csrf_checks=True)
    c.force_login(user)
    return c


def _post_json(client, url):
    return client.post(url, data="{}", content_type="application/json")


# every session-authenticated mutation must reject a request with no CSRF token
def test_checkout_enforces_csrf(user):
    assert _post_json(_client(user), "/api/orders/checkout").status_code == 403


def test_address_verify_enforces_csrf(user):
    assert _post_json(_client(user), "/api/orders/address/verify").status_code == 403


def test_employee_order_transition_enforces_csrf(employee_user):
    assert _post_json(_client(employee_user), "/api/employee/orders/1/transition").status_code == 403


def test_inventory_adjust_enforces_csrf(employee_user):
    assert _post_json(_client(employee_user), "/api/employee/inventory/1/adjust").status_code == 403


def test_role_change_enforces_csrf(employee_user):
    assert _post_json(_client(employee_user), "/api/employee/users/1/role").status_code == 403
