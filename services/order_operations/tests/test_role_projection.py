"""
authorization by capability, projected from identity

one boolean could not distinguish an operator from a manager, so every employee token authorized everything
a role reaches Operations through the authz event and is required on both sides
"""

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import Client

from operations import auth
from operations.models import EmployeeAuthorization

pytestmark = pytest.mark.django_db

SUBJECT = 7
VERSION = 3
OPERATOR = "restaurant_operator"
MANAGER = "restaurant_manager"


@pytest.fixture
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _known_jwks(keypair, monkeypatch):
    monkeypatch.setattr(auth, "_signing_key", lambda token: keypair.public_key())


def _token(keypair, roles, sub=SUBJECT, version=VERSION):
    now = int(time.time())
    return pyjwt.encode(
        {"iss": "identity", "aud": "operations", "sub": str(sub), "roles": roles,
         "authz_version": version, "jti": "x", "iat": now, "exp": now + 600},
        keypair, algorithm="RS256",
    )


def _projected(roles, version=VERSION, active=True):
    return EmployeeAuthorization.objects.create(
        subject_id=SUBJECT, authz_version=version, role_active=bool(roles),
        roles=roles, roles_known=True, user_active=active,
    )


def _get(keypair, roles):
    return Client().get("/ops-api/orders",
                        headers={"authorization": f"Bearer {_token(keypair, roles)}"})


@pytest.mark.parametrize("role", [OPERATOR, MANAGER])
def test_a_projected_role_authorizes_order_access(keypair, role):
    _projected([role])

    assert _get(keypair, [role]).status_code == 200


def test_a_role_the_projection_does_not_know_is_refused(keypair):
    _projected([OPERATOR])

    assert _get(keypair, [MANAGER]).status_code == 401, "a token may not grant what identity did not"


def test_a_role_the_token_does_not_carry_is_refused(keypair):
    _projected([MANAGER])

    assert _get(keypair, []).status_code == 401


def test_a_revoked_subject_is_refused(keypair):
    _projected([])

    assert _get(keypair, [MANAGER]).status_code == 401


def test_a_deactivated_user_is_refused(keypair):
    _projected([MANAGER], active=False)

    assert _get(keypair, [MANAGER]).status_code == 401


def test_a_stale_authorization_version_is_refused(keypair):
    _projected([MANAGER], version=VERSION + 1)

    assert _get(keypair, [MANAGER]).status_code == 401


def test_an_event_without_roles_still_authorizes_the_old_way(keypair):
    """a projection written before roles existed must keep working until the backfill lands"""
    EmployeeAuthorization.objects.create(
        subject_id=SUBJECT, authz_version=VERSION, role_active=True,
        roles=[], roles_known=False, user_active=True,
    )

    assert _get(keypair, [MANAGER]).status_code == 200


def test_holding_no_role_is_not_the_same_as_never_having_been_told(keypair):
    """an empty list from identity is an answer; the boolean must not override it"""
    EmployeeAuthorization.objects.create(
        subject_id=SUBJECT, authz_version=VERSION, role_active=True,
        roles=[], roles_known=True, user_active=True,
    )

    assert _get(keypair, [MANAGER]).status_code == 401
