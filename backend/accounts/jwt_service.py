import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from django.conf import settings
from jwt.algorithms import RSAAlgorithm

from accounts.models import has_operations_role
from accounts.roles import roles_of

ISSUER = "identity"
AUDIENCE = "operations"
ALGORITHM = "RS256"


class NotAuthorized(Exception):
    pass


def _private_pem() -> str:
    if settings.IDENTITY_JWT_PRIVATE_KEY:
        return settings.IDENTITY_JWT_PRIVATE_KEY.replace("\\n", "\n")
    with open(settings.IDENTITY_JWT_PRIVATE_KEY_FILE) as fh:
        return fh.read()


def _private_key():
    return load_pem_private_key(_private_pem().encode(), password=None)


def is_employee(user) -> bool:
    return has_operations_role(user)


def issue_employee_token(user) -> tuple[str, int]:
    # fail closed at issuance: an inactive or non-staff user never receives a token
    if not user.is_active or not has_operations_role(user):
        raise NotAuthorized("user may not receive an operations token")
    ttl = settings.IDENTITY_JWT_TTL
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user.id),
        "roles": roles_of(user),
        "authz_version": user.authz_version,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, _private_key(), algorithm=ALGORITHM, headers={"kid": settings.IDENTITY_JWT_KID})
    return token, ttl


def _jwk(public_key, kid: str) -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "use": "sig", "alg": ALGORITHM})
    return jwk


def _previous_public_pem() -> str | None:
    if settings.IDENTITY_JWT_PREVIOUS_PUBLIC_KEY:
        return settings.IDENTITY_JWT_PREVIOUS_PUBLIC_KEY.replace("\\n", "\n")
    if settings.IDENTITY_JWT_PREVIOUS_PUBLIC_KEY_FILE:
        with open(settings.IDENTITY_JWT_PREVIOUS_PUBLIC_KEY_FILE) as fh:
            return fh.read()
    return None


def public_jwks() -> dict:
    # publish the previous key alongside the current one so tokens signed before a
    # rotation still verify until they expire
    keys = [_jwk(_private_key().public_key(), settings.IDENTITY_JWT_KID)]
    prev = _previous_public_pem()
    if prev and settings.IDENTITY_JWT_PREVIOUS_KID:
        keys.append(_jwk(load_pem_public_key(prev.encode()), settings.IDENTITY_JWT_PREVIOUS_KID))
    return {"keys": keys}
