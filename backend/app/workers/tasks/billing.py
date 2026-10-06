"""
app/workers/tasks/billing.py — Razorpay subscription reconciliation + lapsed-
period enforcement.

Two separate safety nets, both needed because neither Razorpay's webhook nor
its own subscription.status string can be fully trusted alone:

- reconcile_razorpay_subscriptions (daily): corrects local Subscription/org
  state that drifted from a missed webhook, by asking Razorpay directly.
- expire_lapsed_subscriptions (hourly): a backstop independent of Razorpay
  entirely. If Subscription.current_period_end has passed by more than
  BILLING_GRACE_PERIOD_DAYS and no renewal charge has pushed it forward,
  org.is_active is flipped off regardless of what Razorpay's own status still
  says -- Razorpay can keep a subscription "active"/"pending" for days while
  internally retrying a failed charge, and a lost/undelivered webhook would
  otherwise leave an unpaid org with full access indefinitely (see incident:
  an org's period ended and it stayed fully active 3+ days later with nothing
  ever having re-billed it or cut it off). A later subscription.charged
  webhook reactivates the org and moves current_period_end forward again
  either way, so this never fights a subscription that's actually current.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, or_, select

from app.config import settings
from app.core.razorpay_client import RazorpayError, fetch_subscription
from app.database import make_worker_session_factory
from app.models.audit_log import AuditLog
from app.models.subscription import Subscription
from app.models.user import Organization
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

AsyncSessionLocal = make_worker_session_factory()

_TERMINAL_STATUSES = ("cancelled", "completed", "expired")
_ACTIVE_STATUSES = ("authenticated", "active")
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _unix_to_datetime(value: int | None) -> datetime | None:
    return _UNIX_EPOCH + timedelta(seconds=value) if value else None


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
            # Refresh period dates from Razorpay's own record too, not just the
            # status string -- without this, a subscription that actually
            # renewed but whose subscription.charged webhook never arrived
            # would keep the stale current_period_end forever, and
            # expire_lapsed_subscriptions below would (correctly, but
            # needlessly) cut it off on the next run.
            remote_period_end = _unix_to_datetime(remote.get("current_end"))
            period_changed = bool(remote_period_end) and remote_period_end != sub.current_period_end
            if period_changed:
                sub.current_period_start = _unix_to_datetime(remote.get("current_start"))
                sub.current_period_end = remote_period_end

            if remote_status == sub.status and not period_changed:
                continue

            log.info(
                "razorpay_reconcile_status_drift",
                subscription_id=sub.provider_subscription_id,
                local_status=sub.status,
                remote_status=remote_status,
                period_changed=period_changed,
            )
            sub.status = remote_status

            org = await session.get(Organization, sub.org_id)
            if org:
                org.is_active = remote_status in _ACTIVE_STATUSES

        await session.commit()


@celery_app.task(name="app.workers.tasks.billing.reconcile_razorpay_subscriptions", bind=True)
def reconcile_razorpay_subscriptions(self) -> None:
    """Beat task (daily): correct any local Subscription/org state that drifted from a missed webhook."""
    if not settings.BILLING_ENABLED:
        return
    asyncio.run(_reconcile_async())


async def _expire_lapsed_async() -> None:
    """
    Two distinct unpaid situations, both caught here:

    1. current_period_end is set and passed grace -- a subscription that WAS
       paid at least once but hasn't renewed (the common case).
    2. provider == "razorpay" with current_period_end still NULL and created
       more than grace ago -- the mandate was authenticated/activated but a
       first real charge never landed (no subscription.charged webhook ever
       arrived), so the org went "active" without ever actually being billed.

    A subscription with provider IS NULL and no current_period_end (a
    SuperAdmin manually comping a plan with no Razorpay subscription at all,
    see app/api/platform.py) matches neither and is left untouched -- that's
    an intentional admin decision, not a lapsed payment.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BILLING_GRACE_PERIOD_DAYS)

    async with AsyncSessionLocal() as session:
        subs = (await session.execute(
            select(Subscription).where(
                Subscription.deleted_at.is_(None),
                Subscription.status.notin_(_TERMINAL_STATUSES),
                or_(
                    Subscription.current_period_end < cutoff,
                    and_(
                        Subscription.current_period_end.is_(None),
                        Subscription.provider == "razorpay",
                        Subscription.created_at < cutoff,
                    ),
                ),
            )
        )).scalars().all()

        for sub in subs:
            org = await session.get(Organization, sub.org_id)
            never_charged = sub.current_period_end is None

            log.warning(
                "subscription_period_lapsed",
                org_id=str(sub.org_id),
                subscription_id=sub.provider_subscription_id or str(sub.id),
                current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
                never_charged=never_charged,
                grace_days=settings.BILLING_GRACE_PERIOD_DAYS,
            )
            sub.status = "expired"
            if org:
                org.is_active = False

            session.add(AuditLog(
                actor_type="system",
                actor_id=None,
                org_id=sub.org_id,
                action="subscription.period_expired",
                target_type="subscription",
                target_id=sub.id,
                audit_metadata={
                    "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                    "never_charged": never_charged,
                    "grace_period_days": settings.BILLING_GRACE_PERIOD_DAYS,
                },
            ))

        await session.commit()


@celery_app.task(name="app.workers.tasks.billing.expire_lapsed_subscriptions", bind=True)
def expire_lapsed_subscriptions(self) -> None:
    """
    Beat task (hourly): cut off org.is_active for any subscription whose
    current_period_end passed more than BILLING_GRACE_PERIOD_DAYS ago without
    a renewal charge extending it -- the backstop described in this module's
    docstring.
    """
    if not settings.BILLING_ENABLED:
        return
    asyncio.run(_expire_lapsed_async())
