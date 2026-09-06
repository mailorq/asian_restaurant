"""log formatter for the storefront"""

import contextlib
import contextvars
import datetime as dt
import json
import logging
import re

# LogRecord always carries these; anything else on the record came from `extra`
_RESERVED = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info", "taskName",
    "thread", "threadName",
})


_bound: contextvars.ContextVar[dict | None] = contextvars.ContextVar("log_context", default=None)


@contextlib.contextmanager
def log_context(**fields):
    """binds identifiers to every record emitted while the block runs, however deep the caller"""
    token = _bound.set({**(_bound.get() or {}), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _bound.reset(token)


class JsonFormatter(logging.Formatter):
    """renders one JSON object per record, carrying every field passed through `extra`"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_bound.get() or {})
        # the call site is more specific than the surrounding context, so it wins
        payload.update(
            {k: v for k, v in record.__dict__.items()
             if k not in _RESERVED and not k.startswith("_")}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        # default=str keeps a UUID or a datetime in `extra` from breaking the record
        return json.dumps(payload, ensure_ascii=False, default=str)


class RedactBodies(logging.Filter):

    _BODY = re.compile("body_prefix=.*", re.DOTALL)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - a broken record is still worth emitting
            return True
        if "body_prefix=" in rendered:
            record.msg = self._BODY.sub("body_prefix=<redacted>", rendered)
            record.args = ()
        return True
