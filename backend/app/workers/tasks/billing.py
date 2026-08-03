"""
app/workers/tasks/billing.py — Razorpay subscription reconciliation.

Resilience layer behind "automatic enforcement": webhooks are the primary
source of truth for Subscription.status/org.is_active, but webhook delivery
isn't 100% guaranteed. This daily beat task fetches each non-terminal
Razorpay-backed Subscription from Razorpay directly and corrects local state
if it drifted from a missed webhook.
"""
from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.core.razorpay_client import RazorpayError, fetch_subscription
from app.database import make_worker_session_factory
from app.models.subscription import Subscription
from app.models.user import Organization
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

AsyncSessionLocal = make_worker_session_factory()

_TERMINAL_STATUSES = ("cancelled", "completed", "expired")
_ACTIVE_STATUSES = ("authenticated", "active")


async def _reconcile_async() -> None:
    async with AsyncSessionLocal() as session:
        subs = (await session.execute(
            select(Subscription).where(
                Subscription.provider == "razorpay",
                Subscription.deleted_at.is_(None),
                Subscription.status.notin_(_TERMINAL_STATUSES),
            )
        )).scalars().all()

        for sub in subs:
            try:
                remote = await fetch_subscription(sub.provider_subscription_id)
            except RazorpayError as exc:
                log.warning("razorpay_reconcile_fetch_failed", subscription_id=sub.provider_subscription_id, error=str(exc))
                continue

            remote_status = remote.get("status", sub.status)
            if remote_status == sub.status:
                continue

            log.info(
                "razorpay_reconcile_status_drift",
                subscription_id=sub.provider_subscription_id,
                local_status=sub.status,
                remote_status=remote_status,
            )
            sub.status = remote_status

            org = await session.get(Organization, sub.org_id)
            if org:
                org.is_active = remote_status in _ACTIVE_STATUSES

        await session.commit()


@celery_app.task(name="app.workers.tasks.billing.reconcile_razorpay_subscriptions", bind=True)
def reconcile_razorpay_subscriptions(self) -> None:
    """Beat task (daily): correct any local Subscription/org state that drifted from a missed webhook."""
    asyncio.run(_reconcile_async())
