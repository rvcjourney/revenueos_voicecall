"""
logging_config.py — Structured JSON logging + Sentry for the voice agent process.

Mirrors backend/app/core/logging.py's structlog setup so agent logs and
backend logs share the same shape and can be correlated by call_id.

Every log record includes: timestamp (ISO-8601 UTC), level, logger,
call_id, room, campaign_id — populated from context vars via set_log_context().

Usage:
    import structlog
    logger = structlog.get_logger("voice-agent")
    logger.info("event_name", key=value, ...)

Existing %-style stdlib calls (logger.info("msg %s", x)) keep working
unchanged — PositionalArgumentsFormatter() below interpolates them before
rendering, same as the backend does for uvicorn/celery/sqlalchemy.

Call configure_logging() once at process startup, before any log statement.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from config import ENVIRONMENT, LOG_LEVEL, SENTRY_DSN, SENTRY_TRACES_SAMPLE_RATE

# ── Per-call context variables ─────────────────────────────────────────────
# Set via set_log_context(); injected into every log record by _inject_ctx.
_call_id: ContextVar[str] = ContextVar("call_id", default="")
_room: ContextVar[str] = ContextVar("room", default="")
_campaign_id: ContextVar[str] = ContextVar("campaign_id", default="")


def set_log_context(*, call_id: str = "", room: str = "", campaign_id: str = "") -> None:
    """Bind per-call context so all subsequent log calls include it."""
    if call_id:
        _call_id.set(call_id)
    if room:
        _room.set(room)
    if campaign_id:
        _campaign_id.set(campaign_id)


def _inject_ctx(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: merge context vars into every event dict."""
    if cid := _call_id.get():
        event_dict["call_id"] = cid
    if room := _room.get():
        event_dict["room"] = room
    if camp := _campaign_id.get():
        event_dict["campaign_id"] = camp
    return event_dict


def configure_logging() -> None:
    """Configure structlog + stdlib root logger. Call before any log statement."""
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    is_dev = ENVIRONMENT == "development"

    shared: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_ctx,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = structlog.dev.ConsoleRenderer(colors=True) if is_dev else structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def init_sentry() -> None:
    """No-op if SENTRY_DSN is unset — mirrors backend/app/main.py:_init_sentry."""
    if not SENTRY_DSN:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    structlog.get_logger("voice-agent").info("sentry_initialized", environment=ENVIRONMENT)
