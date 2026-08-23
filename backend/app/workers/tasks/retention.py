"""
app/workers/tasks/retention.py — Daily purge of call recordings/transcripts
past CALL_DATA_RETENTION_DAYS (app/config.py; founder decision, 2026-08-23
readiness audit blocker 3: 45 days, hard delete).

The Call row itself is never touched (see app/models/call.py's Call
docstring: "Append-only; never hard or soft deleted (legal/audit)") -- only
two things are removed once a call is older than the retention window:
  - Call.recording_url is cleared. Note this purges our own stored
    reference/access to the recording, not necessarily Vobiz's own copy --
    recordings are fetched live from Vobiz's hosted media (see
    app/core/vobiz.py) rather than mirrored into our own storage, so whether
    the underlying audio is itself deleted depends on Vobiz's own retention
    policy, which this task has no visibility into or control over.
  - The call's CallTranscript row (the actual text we do fully control) is
    hard-deleted.
recording_purged_at is stamped either way so each call is only ever
processed once, regardless of whether it had anything to purge.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update

from app.config import settings
from app.database import make_worker_session_factory
from app.models.call import Call, CallTranscript
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

# NullPool factory, not app.database.AsyncSessionLocal -- this task runs
# under asyncio.run() (a fresh event loop every invocation, see
# app.workers.tasks.campaign/billing for the same convention), and the
# API's pooled engine reuses asyncpg connections tied to a previous loop,
# which crashes cross-loop. See make_worker_session_factory()'s docstring.
AsyncSessionLocal = make_worker_session_factory()

_BATCH_SIZE = 500


async def _purge_expired_call_data_async() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.CALL_DATA_RETENTION_DAYS)
    now = datetime.now(timezone.utc)
    total_purged = 0

    while True:
        async with AsyncSessionLocal() as session:
            call_ids = (await session.execute(
                select(Call.id)
                .where(Call.created_at < cutoff, Call.recording_purged_at.is_(None))
                .limit(_BATCH_SIZE)
            )).scalars().all()

            if not call_ids:
                break

            await session.execute(
                CallTranscript.__table__.delete().where(CallTranscript.call_id.in_(call_ids))
            )
            await session.execute(
                update(Call)
                .where(Call.id.in_(call_ids))
                .values(recording_url=None, recording_purged_at=now)
            )
            await session.commit()

        total_purged += len(call_ids)
        log.info("call_data_purge_batch", purged=len(call_ids), cutoff=cutoff.isoformat())

        if len(call_ids) < _BATCH_SIZE:
            break

    if total_purged:
        log.info("call_data_purge_done", total_purged=total_purged, retention_days=settings.CALL_DATA_RETENTION_DAYS)


@celery_app.task(name="app.workers.tasks.retention.purge_expired_call_data", bind=True)
def purge_expired_call_data(self) -> None:
    """Beat task (daily): hard-delete recordings/transcripts for calls older
    than CALL_DATA_RETENTION_DAYS. See module docstring for exactly what is
    and isn't removed."""
    asyncio.run(_purge_expired_call_data_async())
