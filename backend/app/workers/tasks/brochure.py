"""
app/workers/tasks/brochure.py — email the brochure a customer agreed to on a call.

Queued once per call from app/api/calls.py:agent_report. The work and the
timeline entry live in app/services/brochure.py; a failed send is recorded on
the lead (with the reason) for the team to fix and resend, not retried here.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from app.database import make_worker_session_factory
from app.services.brochure import deliver_brochure_for_call
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)
AsyncSessionLocal = make_worker_session_factory()


async def _send_async(call_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await deliver_brochure_for_call(session, UUID(call_id))
    if result is not None:
        log.info("brochure_delivery", call_id=call_id, ok=result[0], detail=result[1])


@celery_app.task(name="app.workers.tasks.brochure.send_brochure", bind=True, max_retries=0)
def send_brochure(self, call_id: str) -> None:
    asyncio.run(_send_async(call_id))
