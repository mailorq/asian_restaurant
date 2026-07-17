import functools

from django.core.cache import cache
from ninja.errors import HttpError


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _hit(bucket: str, window: int) -> int:
    if cache.add(bucket, 1, window):
        return 1
    try:
        return cache.incr(bucket)
    except ValueError:
        cache.set(bucket, 1, window)
        return 1


def rate_limit(scope: str, limit: int, window: int):
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            bucket = f"rl:{scope}:{_client_ip(request)}"
            try:
                hits = _hit(bucket, window)
            except Exception:
                raise HttpError(503, "Сервис временно недоступен. Повторите позже.")
            if hits > limit:
                raise HttpError(429, "Слишком много запросов. Попробуйте позже.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
