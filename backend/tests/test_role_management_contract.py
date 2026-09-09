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
