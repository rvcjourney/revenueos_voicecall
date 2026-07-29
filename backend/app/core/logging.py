"""
app/core/logging.py — Structured JSON logging via structlog.

Every log record includes: timestamp (ISO-8601 UTC), level, logger,
request_id, org_id, user_id, trace_id — populated from context vars.

Usage:
    import structlog
    log = structlog.get_logger(__name__)
    log.info("event_name", key=value, ...)

Stdlib loggers (uvicorn, SQLAlchemy, celery) are bridged into structlog's
processor chain via ProcessorFormatter, producing identical JSON output.
Call configure_logging() once at application startup.
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# ── Per-request context variables ─────────────────────────────────────────────
# Set via set_log_context(); injected into every log record by _inject_ctx.
_request_id: ContextVar[str] = ContextVar("request_id", default="")
_org_id: ContextVar[str] = ContextVar("org_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def set_log_context(
    *,
    request_id: str = "",
    org_id: str = "",
    user_id: str = "",
    trace_id: str = "",
) -> None:
    """Bind per-request context so all subsequent log calls include it."""
    if request_id:
        _request_id.set(request_id)
    if org_id:
        _org_id.set(org_id)
    if user_id:
        _user_id.set(user_id)
    if trace_id:
        _trace_id.set(trace_id)


def _inject_ctx(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: merge context vars into every event dict."""
    if rid := _request_id.get():
        event_dict["request_id"] = rid
    if oid := _org_id.get():
        event_dict["org_id"] = oid
    if uid := _user_id.get():
        event_dict["user_id"] = uid
    if tid := _trace_id.get():
        event_dict["trace_id"] = tid
    return event_dict


class _BenignPoolCloseFilter(logging.Filter):
    """Demote the known-benign 'connection aborted while closing' pool noise.

    NullPool opens a fresh DB connection per request and closes it right after.
    If the socket was already reset (AV/VPN/firewall interference, or a network
    blip) before the graceful close message could be sent, SQLAlchemy logs it at
    `error` even though it already catches the exception and never fails the
    request (sqlalchemy/pool/base.py `_close_connection`). Demote to `debug` so
    routine cleanup noise doesn't read as a request-breaking failure.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.levelno >= logging.ERROR
            and record.name.startswith("sqlalchemy.pool")
            and record.getMessage().startswith(("Exception closing connection", "Exception terminating connection"))
        ):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


def configure_logging() -> None:
    """
    Configure structlog + stdlib root logger.
    Must be called before any log statement (called in app lifespan).
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    is_dev = settings.ENVIRONMENT == "development"

    # Processors shared by both structlog and stdlib (via ProcessorFormatter)
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_ctx,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = structlog.dev.ConsoleRenderer(colors=True) if is_dev else structlog.processors.JSONRenderer()

    # stdlib handler — used by uvicorn, SQLAlchemy, celery, etc.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(_BenignPoolCloseFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Suppress noisy sub-loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DB_ECHO else logging.WARNING
    )
    logging.getLogger("celery").setLevel(logging.INFO)

    # structlog — routes through the same stdlib handler via ProcessorFormatter
    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ── Request ID middleware ──────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Generates a UUID4 hex per request, seeds the log context, and echoes
    it back as X-Request-ID in the response header.
    Accepts X-Request-ID from upstream proxies (idempotent for retries).
    Accepts X-Trace-ID from Datadog/Caddy for distributed tracing.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        trace_id = request.headers.get("X-Trace-ID", "")
        set_log_context(request_id=request_id, trace_id=trace_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
