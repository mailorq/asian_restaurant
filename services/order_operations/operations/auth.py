import jwt
from django.conf import settings
from ninja.security import HttpBearer

ISSUER = "identity"
AUDIENCE = "operations"
EMPLOYEE_ROLE = "restaurant_employee"

_jwks_client = None


def _client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.IDENTITY_JWKS_URL)
    return _jwks_client


def _signing_key(token: str):
    return _client().get_signing_key_from_jwt(token).key


def _authorized(claims) -> bool:
    # fail closed: the local authorization projection must know this subject at the token's
    # authz_version with an active role and user. Unknown, stale, or an unavailable
    # projection (query error) are all rejected — a valid old token never authorizes.
    from operations.models import EmployeeAuthorization

    try:
        subject = int(claims.get("sub"))
        authz = EmployeeAuthorization.objects.filter(subject_id=subject).first()
    except Exception:
        return False
    return bool(authz and authz.role_active and authz.user_active
                and authz.authz_version == claims.get("authz_version"))


class EmployeeJWTAuth(HttpBearer):
    def authenticate(self, request, token: str):
        # verify signature against Identity's rotating public keys, then the standard
        # claims; the actor is taken from the token, never from client-supplied data
        try:
            claims = jwt.decode(token, _signing_key(token), algorithms=["RS256"],
                                audience=AUDIENCE, issuer=ISSUER)
        except Exception:
            return None
        if EMPLOYEE_ROLE not in claims.get("roles", []):
            return None
        if not _authorized(claims):
            return None
        request.actor_id = claims.get("sub")
        return claims
