"""
app/core/credits.py — Credit-based call billing.

1 credit = 1 minute of call time (rounded up). Shared between the campaign
worker (app/workers/tasks/campaign.py, increments usage when a call ends)
and the SuperAdmin API (app/api/platform.py: manual adjust/reset) and the
org-scoped usage endpoint (app/api/usage.py).

Billing period: tracked independently of the legacy
Organization.calls_used_this_period/monthly_call_quota/billing_period_* fields
(an older, never-wired-up quota mechanism) via last_credit_reset_at. A period
is considered stale (and reset to 0) once it is more than CREDIT_PERIOD_DAYS old.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization

CREDIT_PERIOD_DAYS = 30
# Used only when an org has no active subscription row at all (should be rare —
# every org is expected to carry a Subscription once plans are seeded).
DEFAULT_CREDITS_PER_MONTH = 500


def minutes_for_duration(duration_seconds: int | None) -> int:
    """1 credit = 1 minute of call time, rounded up. None/0/negative → 0."""
    if not duration_seconds or duration_seconds <= 0:
        return 0
    return math.ceil(duration_seconds / 60)


async def _active_subscription(db: AsyncSession, org_id: UUID) -> Subscription | None:
    return await db.scalar(
        select(Subscription).where(
            Subscription.org_id == org_id,
            Subscription.deleted_at.is_(None),
        )
    )


async def resolve_org_credits_per_month(db: AsyncSession, org_id: UUID) -> int:
    """
    Effective monthly credit allotment for the org's *current* period: the
    plan's credits_per_month, unless a mid-period plan change left a prorated
    blend on the subscription (Subscription.prorated_credits_override — see
    app/core/billing.py:compute_blended_monthly_credits).
    """
    sub = await _active_subscription(db, org_id)
    if not sub:
        return DEFAULT_CREDITS_PER_MONTH
    if sub.prorated_credits_override is not None:
        return sub.prorated_credits_override
    plan = await db.get(Plan, sub.plan_id)
    return plan.credits_per_month if plan else DEFAULT_CREDITS_PER_MONTH


async def resolve_org_credit_price_cents(db: AsyncSession, org_id: UUID) -> int:
    """USD cents charged per overage minute. 0 if the org has no active plan."""
    sub = await _active_subscription(db, org_id)
    if not sub:
        return 0
    plan = await db.get(Plan, sub.plan_id)
    return plan.credit_price_cents if plan else 0


async def reset_credit_period(db: AsyncSession, org: Organization, *, now: datetime | None = None) -> None:
    """
    Unconditionally reset credits_used_this_period to 0 and clear any
    mid-period proration blend, since the new period runs at the (possibly
    new) plan's full rate. Caller is responsible for committing.

    Called two ways: lazily via reset_credit_period_if_stale() below (the
    time-based fallback for orgs with no payment provider), and directly by
    the Razorpay webhook handler (app/api/webhooks.py) on subscription.charged,
    since a real charge succeeding is a more precise trigger than a rolling
    30-day timer.
    """
    now = now or datetime.now(timezone.utc)
    org.credits_used_this_period = 0
    org.last_credit_reset_at = now

    sub = await _active_subscription(db, org.id)
    if sub is not None and sub.prorated_credits_override is not None:
        sub.prorated_credits_override = None


async def reset_credit_period_if_stale(
    db: AsyncSession, org: Organization, *, now: datetime | None = None
) -> bool:
    """
    Reset credits_used_this_period to 0 once last_credit_reset_at is more than
    CREDIT_PERIOD_DAYS old. Returns True if a reset happened. Caller is
    responsible for committing.
    """
    now = now or datetime.now(timezone.utc)
    if now - org.last_credit_reset_at < timedelta(days=CREDIT_PERIOD_DAYS):
        return False

    await reset_credit_period(db, org, now=now)
    return True


async def record_call_credits(
    db: AsyncSession, *, org_id: UUID, duration_seconds: int | None
) -> dict:
    """
    Increment credits_used_this_period by the rounded-up minutes for one call.
    Call this only for calls that actually connected — no_answer/failed
    attempts don't consume call-minutes.

    Returns a dict describing what happened so the caller can decide whether
    to record an overage-billing event:
        {
            "minutes_billed": int,             # minutes added by this call
            "credits_used_this_period": int,    # org total after this call
            "credits_per_month": int,           # effective allotment this period
            "overage_minutes": int,             # portion of THIS call's minutes billed as overage
            "overage_cost_cents": int,          # overage_minutes * credit_price_cents
        }
    Does not write any billing/audit record itself — the caller (campaign
    worker) does that, since it has the Call row to attach it to.
    """
    minutes = minutes_for_duration(duration_seconds)

    org = await db.get(Organization, org_id)
    if org is None:
        return {
            "minutes_billed": minutes,
            "credits_used_this_period": 0,
            "credits_per_month": 0,
            "overage_minutes": 0,
            "overage_cost_cents": 0,
        }

    await reset_credit_period_if_stale(db, org)
    credits_per_month = await resolve_org_credits_per_month(db, org_id)

    before = org.credits_used_this_period
    after = before + minutes
    org.credits_used_this_period = after

    overage_before = max(0, before - credits_per_month)
    overage_after = max(0, after - credits_per_month)
    overage_minutes = overage_after - overage_before

    price_cents = await resolve_org_credit_price_cents(db, org_id) if overage_minutes > 0 else 0

    return {
        "minutes_billed": minutes,
        "credits_used_this_period": after,
        "credits_per_month": credits_per_month,
        "overage_minutes": overage_minutes,
        "overage_cost_cents": overage_minutes * price_cents,
    }


async def get_credit_usage(db: AsyncSession, org_id: UUID) -> dict:
    """Org-scoped usage snapshot for GET /api/usage/credits."""
    org = await db.get(Organization, org_id)
    if org is None:
        return {"used": 0, "allotted": DEFAULT_CREDITS_PER_MONTH, "overage_minutes": 0}

    await reset_credit_period_if_stale(db, org)

    credits_per_month = await resolve_org_credits_per_month(db, org_id)
    return {
        "used": org.credits_used_this_period,
        "allotted": credits_per_month,
        "overage_minutes": max(0, org.credits_used_this_period - credits_per_month),
    }
