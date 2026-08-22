import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from operations import auth
from operations.models import EmployeeAuthorization

pytestmark = pytest.mark.django_db


@pytest.fixture
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _known_jwks(keypair, monkeypatch):
    monkeypatch.setattr(auth, "_signing_key", lambda token: keypair.public_key())


@pytest.fixture
def authorized():
    EmployeeAuthorization.objects.create(subject_id=7, authz_version=1, role_active=True, user_active=True)


def _token(key, roles=("restaurant_employee",), aud="operations", iss="identity",
           exp_delta=600, sub="7", authz_version=1):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub, "roles": list(roles),
              "authz_version": authz_version, "jti": "x", "iat": now, "exp": now + exp_delta}
    return pyjwt.encode(claims, key, algorithm="RS256")


def _authenticate(token):
    return auth.EmployeeJWTAuth().authenticate(SimpleNamespace(), token)


def test_valid_employee_token_authenticates(keypair, authorized):
    claims = _authenticate(_token(keypair))
    assert claims and claims["sub"] == "7"


def test_non_employee_role_rejected(keypair, authorized):
    assert _authenticate(_token(keypair, roles=())) is None


def test_expired_token_rejected(keypair, authorized):
    assert _authenticate(_token(keypair, exp_delta=-10)) is None


def test_wrong_audience_rejected(keypair, authorized):
    assert _authenticate(_token(keypair, aud="storefront")) is None


def test_wrong_issuer_rejected(keypair, authorized):
    assert _authenticate(_token(keypair, iss="rogue")) is None


def test_unknown_signing_key_rejected(keypair, authorized):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _authenticate(_token(other)) is None


def test_unknown_subject_rejected(keypair):
    # no authorization projection for this subject -> fail closed
    assert _authenticate(_token(keypair, sub="999")) is None


def test_stale_authz_version_rejected(keypair, authorized):
    EmployeeAuthorization.objects.filter(subject_id=7).update(authz_version=2)
    assert _authenticate(_token(keypair, authz_version=1)) is None


def test_revoked_role_rejected(keypair, authorized):
    EmployeeAuthorization.objects.filter(subject_id=7).update(role_active=False)
    assert _authenticate(_token(keypair)) is None


def test_inactive_user_rejected(keypair, authorized):
    EmployeeAuthorization.objects.filter(subject_id=7).update(user_active=False)
    assert _authenticate(_token(keypair)) is None
