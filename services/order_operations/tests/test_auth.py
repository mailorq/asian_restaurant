import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from operations import auth


@pytest.fixture
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _known_jwks(keypair, monkeypatch):
    # the JWKS the verifier trusts is this test keypair's public half
    monkeypatch.setattr(auth, "_signing_key", lambda token: keypair.public_key())


def _token(key, roles=("restaurant_employee",), aud="operations", iss="identity", exp_delta=600, sub="7"):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub, "roles": list(roles),
              "authz_version": 1, "jti": "x", "iat": now, "exp": now + exp_delta}
    return pyjwt.encode(claims, key, algorithm="RS256")


def _authenticate(token):
    return auth.EmployeeJWTAuth().authenticate(SimpleNamespace(), token)


def test_valid_employee_token_authenticates(keypair):
    claims = _authenticate(_token(keypair))
    assert claims and claims["sub"] == "7"


def test_non_employee_role_rejected(keypair):
    assert _authenticate(_token(keypair, roles=())) is None


def test_expired_token_rejected(keypair):
    assert _authenticate(_token(keypair, exp_delta=-10)) is None


def test_wrong_audience_rejected(keypair):
    assert _authenticate(_token(keypair, aud="storefront")) is None


def test_wrong_issuer_rejected(keypair):
    assert _authenticate(_token(keypair, iss="rogue")) is None


def test_unknown_signing_key_rejected(keypair):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert _authenticate(_token(other)) is None
