"""
Centralized logging configuration.

One `configure_logging()` call at startup owns the entire logging tree — every
module just does `logging.getLogger(__name__)` and inherits handlers/format.
Previously `logging.basicConfig(level=INFO)` was called inline in main.py, which
(a) silently no-ops if any imported library already touched the root logger, and
(b) produced unparseable free-text logs in production where an aggregator needs
structured fields.

`LOG_FORMAT=json` emits one JSON object per line (Loki/CloudWatch/Datadog ingest
it directly); `LOG_FORMAT=console` stays human-readable for local dev. Either
way the current request's correlation ID is attached automatically via a
ContextVar, so every line emitted while handling a request — including from deep
inside a service that knows nothing about HTTP — is traceable back to it.
"""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

# Set by RequestContextMiddleware; read by the formatters below.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        # Anything passed via logger.info(..., extra={...}) is promoted to a
        # top-level field so it is queryable in the aggregator.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m",
        "WARNING": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        rid = getattr(record, "request_id", "-")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        base = f"{ts} {color}{record.levelname:<8}{self.RESET} [{rid[:8]}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    """Idempotent: safe to call from the app, from Celery, and from scripts."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.LOG_FORMAT == "json" else ConsoleFormatter())
    handler.addFilter(RequestIdFilter())

    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # These libraries are extremely chatty at INFO and drown out application
    # logs; their WARNING+ output is still surfaced.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "chromadb", "faiss"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_request_id() -> str | None:
    return request_id_ctx.get()
