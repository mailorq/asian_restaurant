import jwt
from django.conf import settings
from ninja.security import HttpBearer

ISSUER = "identity"
AUDIENCE = "operations"
EMPLOYEE_ROLE = "restaurant_employee"
STAFF_ROLES = frozenset({"restaurant_operator", "restaurant_manager", EMPLOYEE_ROLE})

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
    if not (authz and authz.user_active and authz.authz_version == claims.get("authz_version")):
        return False
    if not authz.roles_known:
        # identity has never sent roles for this subject; the boolean is all this projection has
        return bool(authz.role_active)
    projected = set(authz.roles or [])
    # the capability must hold on both sides: a token cannot grant what identity did not
    return bool(projected & set(claims.get("roles") or []))


class EmployeeJWTAuth(HttpBearer):
    def authenticate(self, request, token: str):
        # verify signature against Identity's rotating public keys, then the standard
        # claims; the actor is taken from the token, never from client-supplied data
        try:
            claims = jwt.decode(token, _signing_key(token), algorithms=["RS256"],
                                audience=AUDIENCE, issuer=ISSUER)
        except Exception:
            return None
        if not (set(claims.get("roles") or []) & STAFF_ROLES):
            return None
        if not _authorized(claims):
            return None
        # typed here so no handler re-parses the token; _authorized already proved sub is an int
        request.actor_id = int(claims["sub"])
        request.actor_authz_version = claims["authz_version"]
        return claims
