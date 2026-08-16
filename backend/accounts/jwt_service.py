import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings
from jwt.algorithms import RSAAlgorithm

from accounts.models import EMPLOYEE_GROUP

ISSUER = "identity"
AUDIENCE = "operations"
ALGORITHM = "RS256"


def _private_pem() -> str:
    if settings.IDENTITY_JWT_PRIVATE_KEY:
        return settings.IDENTITY_JWT_PRIVATE_KEY.replace("\\n", "\n")
    with open(settings.IDENTITY_JWT_PRIVATE_KEY_FILE) as fh:
        return fh.read()


def _private_key():
    return load_pem_private_key(_private_pem().encode(), password=None)


def is_employee(user) -> bool:
    return user.is_superuser or user.groups.filter(name=EMPLOYEE_GROUP).exists()


def issue_employee_token(user) -> tuple[str, int]:
    ttl = settings.IDENTITY_JWT_TTL
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user.id),
        "roles": [EMPLOYEE_GROUP] if is_employee(user) else [],
        "authz_version": user.authz_version,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, _private_key(), algorithm=ALGORITHM, headers={"kid": settings.IDENTITY_JWT_KID})
    return token, ttl


def public_jwks() -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(_private_key().public_key()))
    jwk.update({"kid": settings.IDENTITY_JWT_KID, "use": "sig", "alg": ALGORITHM})
    return {"keys": [jwk]}
