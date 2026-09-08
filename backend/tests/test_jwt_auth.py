import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from accounts import jwt_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def signing(settings):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.IDENTITY_JWT_PRIVATE_KEY = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    settings.IDENTITY_JWT_PRIVATE_KEY_FILE = ""
    return key


def _decode(token, public_key):
    return pyjwt.decode(token, public_key, algorithms=["RS256"], audience="operations", issuer="identity")


def test_issue_employee_token_claims(signing, employee_user):
    token, ttl = jwt_service.issue_employee_token(employee_user)
    claims = _decode(token, signing.public_key())
    assert claims["sub"] == str(employee_user.id)
    assert "restaurant_manager" in claims["roles"]
    assert claims["authz_version"] == employee_user.authz_version
    assert ttl == 600


def test_customer_cannot_get_operations_token(signing, user):
    with pytest.raises(jwt_service.NotAuthorized):
        jwt_service.issue_employee_token(user)


def test_inactive_employee_cannot_get_token(signing, employee_user):
    employee_user.is_active = False
    employee_user.save(update_fields=["is_active"])
    with pytest.raises(jwt_service.NotAuthorized):
        jwt_service.issue_employee_token(employee_user)


def test_jwks_is_public_and_matches_signing_key(signing, api):
    body = api.get("/api/auth/jwks").json()
    key = body["keys"][0]
    assert key["kty"] == "RSA" and key["use"] == "sig" and key["kid"]


def test_employee_token_endpoint_authorization(signing, api, user, employee_user):
    assert api.post("/api/auth/employee-token").status_code == 401  # anonymous

    api.force_login(user)
    assert api.post("/api/auth/employee-token").status_code == 403  # customer, not staff

    api.force_login(employee_user)
    resp = api.post("/api/auth/employee-token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 600
    claims = _decode(body["token"], signing.public_key())
    assert "restaurant_manager" in claims["roles"]
