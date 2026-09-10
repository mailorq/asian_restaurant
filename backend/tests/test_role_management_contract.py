"""the contract the role UI has to speak

the panel used to send a boolean. after the split into two roles a boolean cannot say which one,
so the request must name the role, and the response must say which one the user holds
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.roles import StaffRole

pytestmark = pytest.mark.django_db

ROLE_PATH = "/api/employee/users/{}/role"


def _post(api, user_id, body):
    return api.post(ROLE_PATH.format(user_id), data=json.dumps(body),
                    content_type="application/json")


@pytest.fixture
def target(db):
    return get_user_model().objects.create_user(username="+79990000601", password="Pass!2345")


@pytest.mark.parametrize("role", [StaffRole.OPERATOR, StaffRole.MANAGER])
def test_a_superuser_assigns_either_role_by_name(api, superuser, target, role):
    api.force_login(superuser)

    response = _post(api, target.id, {"role": role})

    assert response.status_code == 200
    assert response.json()["staff_role"] == role
    target.refresh_from_db()
    assert [g.name for g in target.groups.all()] == [role]


def test_an_explicit_null_revokes_the_role(api, superuser, target):
    target.groups.add(Group.objects.get_or_create(name=StaffRole.MANAGER)[0])
    api.force_login(superuser)

    response = _post(api, target.id, {"role": None})

    assert response.status_code == 200
    assert response.json()["staff_role"] is None
    target.refresh_from_db()
    assert list(target.groups.all()) == []


def test_an_empty_body_is_refused_rather_than_read_as_a_revoke(api, superuser, target):
    target.groups.add(Group.objects.get_or_create(name=StaffRole.MANAGER)[0])
    api.force_login(superuser)

    response = _post(api, target.id, {})

    assert response.status_code == 422
    target.refresh_from_db()
    assert [g.name for g in target.groups.all()] == [StaffRole.MANAGER]


def test_the_old_boolean_body_is_refused(api, superuser, target):
    api.force_login(superuser)

    assert _post(api, target.id, {"grant": True}).status_code == 422


def test_an_unknown_role_is_refused(api, superuser, target):
    api.force_login(superuser)

    assert _post(api, target.id, {"role": "restaurant_admin"}).status_code == 422


def test_a_superuser_target_cannot_be_given_a_staff_role(api, superuser, django_user_model):
    """clearing a role on a superuser would report a revoke while every right stays"""
    other = django_user_model.objects.create_superuser(username="+79990000602", password="Pass!2345")
    api.force_login(superuser)

    response = _post(api, other.id, {"role": None})

    assert response.status_code == 409
    other.refresh_from_db()
    assert other.is_superuser


def test_the_listing_says_which_role_each_user_holds(api, superuser, target):
    target.groups.add(Group.objects.get_or_create(name=StaffRole.OPERATOR)[0])
    api.force_login(superuser)

    users = {u["id"]: u for u in api.get("/api/employee/users").json()["items"]}

    assert users[target.id]["staff_role"] == StaffRole.OPERATOR
    assert users[superuser.id]["staff_role"] is None
    assert users[superuser.id]["is_superuser"] is True


def test_the_card_says_which_role_the_user_holds(api, superuser, target):
    target.groups.add(Group.objects.get_or_create(name=StaffRole.MANAGER)[0])
    api.force_login(superuser)

    body = api.get(f"/api/employee/users/{target.id}").json()

    assert body["staff_role"] == StaffRole.MANAGER
    assert body["is_superuser"] is False


def test_the_session_endpoint_reports_the_role_for_tab_visibility(api, superuser):
    from django.contrib.auth.models import Group

    superuser.groups.add(Group.objects.get_or_create(name=StaffRole.OPERATOR)[0])
    api.force_login(superuser)

    body = api.get("/api/auth/me").json()

    assert "staff_role" in body, "the panel cannot decide which tabs to show without it"


def test_the_service_itself_refuses_a_superuser_target(superuser, django_user_model):
    """the endpoint is one caller of many; the CLI reaches this without a view"""
    from accounts.models import EmployeeRoleAudit
    from accounts.roles import InvalidRoleTarget, StaffRole, set_staff_role
    from orders.models import OrderOutbox

    other = django_user_model.objects.create_superuser(username="+79990000801", password="Pass!2345")
    version_before = other.authz_version
    outbox_before = OrderOutbox.objects.count()

    with pytest.raises(InvalidRoleTarget):
        set_staff_role(actor=superuser, target=other, role=StaffRole.MANAGER)

    other.refresh_from_db()
    assert list(other.groups.all()) == []
    assert other.authz_version == version_before
    assert not EmployeeRoleAudit.objects.filter(target=other).exists()
    assert OrderOutbox.objects.count() == outbox_before


def test_the_service_refuses_clearing_a_superuser_role_too(superuser, django_user_model):
    from accounts.roles import InvalidRoleTarget, set_staff_role

    other = django_user_model.objects.create_superuser(username="+79990000802", password="Pass!2345")

    with pytest.raises(InvalidRoleTarget):
        set_staff_role(actor=superuser, target=other, role=None)


def test_a_target_promoted_after_the_api_check_is_still_refused(superuser, target, monkeypatch):
    """the endpoint reads the target before the domain takes its lock"""
    from accounts.roles import InvalidRoleTarget, StaffRole, set_staff_role

    stale = get_user_model().objects.get(pk=target.pk)  # not a superuser yet
    get_user_model().objects.filter(pk=target.pk).update(is_superuser=True)

    with pytest.raises(InvalidRoleTarget):
        set_staff_role(actor=superuser, target=stale, role=StaffRole.OPERATOR)

    target.refresh_from_db()
    assert list(target.groups.all()) == []


def test_the_cli_cannot_give_a_superuser_a_staff_role(superuser, django_user_model):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    other = django_user_model.objects.create_superuser(username="+79990000803", password="Pass!2345")

    with pytest.raises(CommandError):
        call_command("grant_employee", other.username, "--role", "restaurant_manager",
                     "--actor", superuser.username)

    other.refresh_from_db()
    assert list(other.groups.all()) == []


def test_the_session_endpoint_reports_an_operator_exactly(api, django_user_model):
    from django.contrib.auth.models import Group

    from accounts.roles import StaffRole

    operator = django_user_model.objects.create_user(username="+79990000804", password="Pass!2345")
    operator.groups.add(Group.objects.get_or_create(name=StaffRole.OPERATOR)[0])
    api.force_login(operator)

    body = api.get("/api/auth/me").json()

    assert body["staff_role"] == StaffRole.OPERATOR
    assert body["is_superuser"] is False
    assert body["is_employee"] is True
