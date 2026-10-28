"""
app/workers/tasks/webhook.py — deliver the org's call.completed webhook.

Queued from app/api/calls.py:agent_report (once per call). Retries with
backoff on network errors / non-2xx; gives up after MAX_ATTEMPTS and logs.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from app.core import webhook_delivery as wd
from app.core.crypto import decrypt_value
from app.database import make_worker_session_factory
from app.models.call import Call, CallTranscript
from app.models.campaign import CampaignContact
from app.models.user import Organization
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)
AsyncSessionLocal = make_worker_session_factory()

MAX_ATTEMPTS = 5


async def _send_async(call_id: str) -> None:
    async with AsyncSessionLocal() as session:
        call = await session.get(Call, UUID(call_id))
        if call is None:
            return
        org = await session.get(Organization, call.org_id)
        if org is None or not org.webhook_url or not org.webhook_secret:
            return
        contact = await session.get(CampaignContact, call.contact_id) if call.contact_id else None
        transcript = (await session.execute(
            select(CallTranscript).where(CallTranscript.call_id == call.id)
        )).scalar_one_or_none()
        body = wd.encode(wd.build_payload(call, contact, transcript.segments if transcript else []))
        url, secret = org.webhook_url, decrypt_value(org.webhook_secret)

    wd.assert_public_https_url(url)  # re-check at send time, not only when saved
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        resp = await client.post(
            url,
            content=body,
            headers={"Content-Type": "application/json", "X-MOTM-Signature": wd.sign(secret, body)},
        )
    resp.raise_for_status()


@celery_app.task(name="app.workers.tasks.webhook.deliver_webhook", bind=True, max_retries=MAX_ATTEMPTS - 1)
def deliver_webhook(self, call_id: str) -> None:
    try:
        asyncio.run(_send_async(call_id))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            log.error("webhook_delivery_gave_up", call_id=call_id, error=str(exc))
            return
        log.warning("webhook_delivery_retry", call_id=call_id, error=str(exc), attempt=self.request.retries + 1)
        raise self.retry(exc=exc, countdown=30 * 4 ** self.request.retries)  # 30s, 2m, 8m, 32m
