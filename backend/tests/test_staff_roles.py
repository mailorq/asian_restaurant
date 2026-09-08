"""
separation of duties between staff roles

one group granted order handling, stock adjustment, the customer directory and every customer's phone and address at once
an operator who processes orders has no business reading that
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.roles import StaffRole

pytestmark = pytest.mark.django_db

ORDER_ROUTES = ["/api/employee/orders", "/api/employee/orders/1"]
MANAGER_ROUTES = ["/api/employee/inventory", "/api/employee/users", "/api/employee/users/1"]


def _staff(username, role):
    user = get_user_model().objects.create_user(username=username, password="Pass!2345")
    if role is not None:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


@pytest.fixture
def operator():
    return _staff("+79990000021", StaffRole.OPERATOR)


@pytest.fixture
def manager():
    return _staff("+79990000022", StaffRole.MANAGER)


def test_an_operator_reaches_the_order_queue(api, operator):
    api.force_login(operator)

    assert api.get(ORDER_ROUTES[0]).status_code == 200


@pytest.mark.parametrize("path", MANAGER_ROUTES)
def test_an_operator_is_refused_the_manager_area(api, operator, path):
    api.force_login(operator)

    assert api.get(path).status_code == 403, f"{path} exposes stock or customer data to an operator"


def test_an_operator_cannot_adjust_stock(api, operator, make_product):
    product = make_product(stock=5)
    api.force_login(operator)

    response = api.post(f"/api/employee/inventory/{product.id}/adjust",
                        data=json.dumps({"new_quantity": 99, "reason": "проверка прав"}),
                        content_type="application/json")

    assert response.status_code == 403
    product.refresh_from_db()
    assert product.stock_quantity == 5


@pytest.mark.parametrize("path", MANAGER_ROUTES)
def test_a_manager_reaches_the_manager_area(api, manager, path):
    api.force_login(manager)

    assert api.get(path).status_code in (200, 404)


def test_a_manager_still_handles_orders(api, manager):
    api.force_login(manager)

    assert api.get(ORDER_ROUTES[0]).status_code == 200


def test_a_customer_reaches_nothing(api, user):
    api.force_login(user)

    for path in ORDER_ROUTES + MANAGER_ROUTES:
        assert api.get(path).status_code == 403, path


def test_a_superuser_keeps_every_capability(api, superuser):
    api.force_login(superuser)

    for path in [ORDER_ROUTES[0]] + MANAGER_ROUTES:
        assert api.get(path).status_code in (200, 404), path


def test_only_a_superuser_assigns_roles(api, manager, operator):
    api.force_login(manager)

    response = api.post(f"/api/employee/users/{operator.id}/role",
                        data=json.dumps({"role": StaffRole.MANAGER}),
                        content_type="application/json")

    assert response.status_code == 403
    assert StaffRole.MANAGER not in [g.name for g in operator.groups.all()]


def test_a_staff_member_holds_at_most_one_role(superuser, operator):
    from accounts.roles import set_staff_role

    set_staff_role(actor=superuser, target=operator, role=StaffRole.MANAGER)

    operator.refresh_from_db()
    assert sorted(g.name for g in operator.groups.all()) == [StaffRole.MANAGER]


def test_changing_a_role_bumps_the_authorization_version(superuser, operator):
    from accounts.roles import set_staff_role

    before = operator.authz_version
    set_staff_role(actor=superuser, target=operator, role=StaffRole.MANAGER)
    operator.refresh_from_db()
    bumped = operator.authz_version

    set_staff_role(actor=superuser, target=operator, role=StaffRole.MANAGER)
    operator.refresh_from_db()

    assert bumped == before + 1
    assert operator.authz_version == bumped, "an unchanged role must not invalidate live tokens"


def test_the_token_carries_the_role_the_user_actually_holds(operator, manager):
    import jwt as pyjwt

    from accounts import jwt_service

    for user, expected in ((operator, StaffRole.OPERATOR), (manager, StaffRole.MANAGER)):
        token, _ = jwt_service.issue_employee_token(user)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["roles"] == [expected], f"{user.username} got {claims['roles']}"


def test_the_backfill_covers_every_role_not_just_the_legacy_group(operator, manager, superuser):
    from django.core.management import call_command

    from orders.models import OrderOutbox

    OrderOutbox.objects.filter(event_type="identity.authz_changed").delete()
    call_command("emit_authz_state")

    emitted = {
        row.payload["subject_id"]
        for row in OrderOutbox.objects.filter(event_type="identity.authz_changed")
    }
    assert {operator.id, manager.id, superuser.id} <= emitted, "an operator would never be projected"
