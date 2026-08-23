"""
app/core/sentry.py — Shared Sentry init for both the API process (app/main.py)
and the Celery worker/beat processes (app/workers/celery_app.py).

Previously only app/main.py called sentry_sdk.init() -- the worker and beat
processes never initialized Sentry at all, so every error inside a Celery
task (campaign dispatch, billing reconciliation, backups, the retention
purge) was invisible to it, including the Redis-fail-open branches in
app/workers/tasks/campaign.py that are already logged at ERROR level
specifically so they'd be alerting-visible. structlog routes through stdlib
logging (app/core/logging.py), which Sentry's default LoggingIntegration
already turns into Sentry events at ERROR level -- but only in a process
that actually called sentry_sdk.init() first.
"""
from __future__ import annotations

import sentry_sdk
import structlog

from app.config import settings

log = structlog.get_logger(__name__)


def init_sentry(*, integrations: list, component: str) -> None:
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        integrations=integrations,
    )
    log.info("sentry_initialized", environment=settings.ENVIRONMENT, component=component)
