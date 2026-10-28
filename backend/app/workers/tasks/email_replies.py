"""
app/workers/tasks/email_replies.py — count replies to lead emails.

Beat task (every 5 min). For each org with an IMAP host, read the headers of
new INBOX messages (app/core/mail_inbox.py) and match them to a lead:
  1. by thread: In-Reply-To/References contains a Message-ID we sent, else
  2. by sender: the From address is a lead we have emailed.
A match adds an "email_reply" timeline entry (once per reply Message-ID) and
sets the lead's email status to "replied".
"""
from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import func, select

from app.core.email_sender import org_smtp_config
from app.core.mail_inbox import InboxMessage, fetch_new_messages
from app.database import make_worker_session_factory
from app.models.lead import Lead, LeadActivity, LeadActivityType, LeadEmailStatus
from app.models.user import Organization
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)
AsyncSessionLocal = make_worker_session_factory()


async def record_replies(session, org: Organization, messages: list[InboxMessage]) -> int:
    """Match messages to this org's leads and record new replies. Returns how many were recorded."""
    if not messages:
        return 0
    own = (org.smtp_from_email or "").lower()
    sent = dict((await session.execute(
        select(LeadActivity.payload["message_id"].astext, LeadActivity.lead_id).where(
            LeadActivity.org_id == org.id, LeadActivity.type == LeadActivityType.EMAIL,
            LeadActivity.payload["message_id"].astext.is_not(None),
        )
    )).all())
    emailed = dict((await session.execute(
        select(func.lower(Lead.email), Lead.id).where(
            Lead.org_id == org.id, Lead.deleted_at.is_(None), Lead.email.is_not(None),
            Lead.email_status.in_([LeadEmailStatus.SENT, LeadEmailStatus.REPLIED, LeadEmailStatus.FAILED]),
        )
    )).all())
    seen = set((await session.execute(
        select(LeadActivity.payload["message_id"].astext).where(
            LeadActivity.org_id == org.id, LeadActivity.type == LeadActivityType.EMAIL_REPLY,
            LeadActivity.payload["message_id"].astext.in_([m.message_id for m in messages if m.message_id]),
        )
    )).scalars().all())

    recorded = 0
    for m in messages:
        if m.from_email == own or (m.message_id and m.message_id in seen):
            continue
        lead_id = next((sent[t] for t in m.thread_ids if t in sent), None) or emailed.get(m.from_email)
        if lead_id is None:
            continue
        lead = await session.get(Lead, lead_id)
        if lead is None or lead.deleted_at is not None:
            continue
        lead.email_status = LeadEmailStatus.REPLIED
        session.add(LeadActivity(
            org_id=org.id, lead_id=lead.id, type=LeadActivityType.EMAIL_REPLY,
            payload={"from": m.from_email, "subject": m.subject, "date": m.date, "message_id": m.message_id},
        ))
        seen.add(m.message_id)
        recorded += 1
    return recorded


async def _check_org(org_id) -> None:
    async with AsyncSessionLocal() as session:
        org = await session.get(Organization, org_id)
        cfg = org_smtp_config(org)
        if cfg is None or not org.imap_host:
            return
        try:
            messages, last_uid = await asyncio.to_thread(
                fetch_new_messages, org.imap_host, cfg.username, cfg.password, org.imap_last_uid,
            )
        except Exception as exc:  # InboxError or anything else: one org's broken mailbox must not stop the others
            log.warning("email_replies_fetch_failed", org_id=str(org_id), error=str(exc)[:300])
            return
        recorded = await record_replies(session, org, messages)
        org.imap_last_uid = last_uid
        await session.commit()
    if recorded:
        log.info("email_replies_recorded", org_id=str(org_id), count=recorded)


async def _check_all() -> None:
    async with AsyncSessionLocal() as session:
        org_ids = (await session.execute(
            select(Organization.id).where(
                Organization.imap_host.is_not(None), Organization.smtp_password.is_not(None),
                Organization.is_active.is_(True), Organization.deleted_at.is_(None),
            )
        )).scalars().all()
    for org_id in org_ids:
        await _check_org(org_id)


@celery_app.task(name="app.workers.tasks.email_replies.check_email_replies", bind=True)
def check_email_replies(self) -> None:
    asyncio.run(_check_all())
