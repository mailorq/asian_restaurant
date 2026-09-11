import sys

from django.http import JsonResponse
from django.views.defaults import server_error as default_server_error
from psycopg_pool import PoolTimeout

from operations.metrics import db_pool_exhausted


def _pool_exhausted(exc: BaseException | None) -> bool:
    # django re raises the pool's PoolTimeout as its own OperationalError
    while exc is not None:
        if isinstance(exc, PoolTimeout):
            return True
        exc = exc.__cause__
    return False


def server_error(request):
    if _pool_exhausted(sys.exc_info()[1]):
        db_pool_exhausted.inc()
        response = JsonResponse({"detail": "service temporarily unavailable"}, status=503)
        response["Retry-After"] = "1"
        return response
    return default_server_error(request)
