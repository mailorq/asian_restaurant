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
        request.actor_id = claims.get("sub")
        return claims
