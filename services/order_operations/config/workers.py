from uvicorn.workers import UvicornWorker


class BoundedUvicornWorker(UvicornWorker):
    # under ASGI every request runs in a thread of its own. past this many in flight uvicorn answers 503 without starting one, so a burst cannot run the container out of pids, where asgiref leaks the threads it fails to join
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "limit_concurrency": 32}
