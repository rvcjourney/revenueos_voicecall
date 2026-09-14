"""
tests/test_subscription_expiry.py — app/workers/tasks/billing.py's
expire_lapsed_subscriptions backstop (and the reconcile task's period-date
refresh), covering the incident this exists for: a subscription whose
current_period_end passed with no renewal charge landing, and no Razorpay
webhook ever telling us either way, must not leave the org fully active
forever.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization
from app.workers.tasks.billing import _expire_lapsed_async, _reconcile_async


async def _make_plan(db) -> Plan:
    plan = Plan(
        name=f"Plan-{uuid.uuid4().hex[:6]}",
        price_minor=499_900,
        monthly_call_quota=500,
        max_concurrent_calls=3,
        credits_per_month=500,
        is_active=True,
    )
    db.add(plan)
    await db.flush()
    return plan


async def _make_org_with_subscription(db, plan: Plan, **sub_overrides) -> tuple[Organization, Subscription]:
    org = Organization(
        name=f"Org {uuid.uuid4().hex[:6]}",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        is_active=sub_overrides.pop("org_is_active", True),
    )
    db.add(org)
    await db.flush()

    sub_kwargs = dict(org_id=org.id, plan_id=plan.id, status="active")
    sub_kwargs.update(sub_overrides)
    sub = Subscription(**sub_kwargs)
    db.add(sub)
    await db.commit()
    await db.refresh(org)
    await db.refresh(sub)
    return org, sub


async def test_expires_subscription_past_grace_period(db):
    plan = await _make_plan(db)
    lapsed = datetime.now(timezone.utc) - timedelta(days=settings.BILLING_GRACE_PERIOD_DAYS + 1)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_lapsed",
        current_period_end=lapsed,
    )

    await _expire_lapsed_async()

    await db.refresh(org)
    await db.refresh(sub)
    assert org.is_active is False
    assert sub.status == "expired"

    audit = (await db.execute(
        select(AuditLog).where(AuditLog.org_id == org.id, AuditLog.action == "subscription.period_expired")
    )).scalar_one_or_none()
    assert audit is not None


async def test_does_not_expire_subscription_within_grace_period(db):
    plan = await _make_plan(db)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_recent",
        current_period_end=recent,
    )

    await _expire_lapsed_async()

    await db.refresh(org)
    await db.refresh(sub)
    assert org.is_active is True
    assert sub.status == "active"


async def test_expires_razorpay_subscription_never_actually_charged(db):
    """Mandate authenticated/activated, but no subscription.charged webhook
    ever landed -- current_period_end is still NULL. Must still eventually
    expire (unlike a true no-provider SuperAdmin comp, see the test below),
    otherwise an org can go permanently "active" without ever being billed
    once."""
    plan = await _make_plan(db)
    old_created_at = datetime.now(timezone.utc) - timedelta(days=settings.BILLING_GRACE_PERIOD_DAYS + 1)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_never_charged",
        created_at=old_created_at,
    )

    await _expire_lapsed_async()

    await db.refresh(org)
    await db.refresh(sub)
    assert org.is_active is False
    assert sub.status == "expired"


async def test_does_not_expire_freshly_created_razorpay_subscription_awaiting_first_charge(db):
    """A subscription that just went through checkout hasn't had time for its
    subscription.charged webhook to land yet -- must not be punished for
    that within the grace window."""
    plan = await _make_plan(db)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_just_created",
    )

    await _expire_lapsed_async()

    await db.refresh(org)
    await db.refresh(sub)
    assert org.is_active is True
    assert sub.status == "active"


async def test_does_not_touch_subscription_with_no_period_end(db):
    """SuperAdmin-comped plans (no Razorpay subscription) have no
    current_period_end at all -- this is an intentional admin decision, not a
    lapsed payment, and must never be auto-expired."""
    plan = await _make_plan(db)
    org, sub = await _make_org_with_subscription(db, plan)

    await _expire_lapsed_async()

    await db.refresh(org)
    await db.refresh(sub)
    assert org.is_active is True
    assert sub.status == "active"


async def test_does_not_reexpire_already_cancelled_subscription(db):
    plan = await _make_plan(db)
    lapsed = datetime.now(timezone.utc) - timedelta(days=settings.BILLING_GRACE_PERIOD_DAYS + 10)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_cancelled",
        current_period_end=lapsed, status="cancelled", org_is_active=False,
    )

    await _expire_lapsed_async()

    audit_count = len((await db.execute(
        select(AuditLog).where(AuditLog.org_id == org.id, AuditLog.action == "subscription.period_expired")
    )).scalars().all())
    assert audit_count == 0


async def test_reconcile_refreshes_period_end_from_razorpay_and_keeps_org_active(db):
    """A subscription that actually renewed on Razorpay's side but whose
    subscription.charged webhook never arrived: reconcile should pick up the
    new current_period_end from Razorpay directly, not just the status
    string -- otherwise expire_lapsed_subscriptions would incorrectly cut the
    org off on its next run despite the renewal having gone through."""
    plan = await _make_plan(db)
    stale_end = datetime.now(timezone.utc) - timedelta(days=settings.BILLING_GRACE_PERIOD_DAYS + 1)
    new_start = datetime.now(timezone.utc) - timedelta(days=1)
    new_end = datetime.now(timezone.utc) + timedelta(days=29)
    org, sub = await _make_org_with_subscription(
        db, plan, provider="razorpay", provider_subscription_id="sub_renewed",
        current_period_end=stale_end,
    )

    remote = {
        "status": "active",
        "current_start": int(new_start.timestamp()),
        "current_end": int(new_end.timestamp()),
    }
    with patch("app.workers.tasks.billing.fetch_subscription", new=AsyncMock(return_value=remote)):
        await _reconcile_async()

    await db.refresh(sub)
    await db.refresh(org)
    assert sub.current_period_end is not None
    assert sub.current_period_end > datetime.now(timezone.utc)
    assert org.is_active is True

    await _expire_lapsed_async()
    await db.refresh(org)
    assert org.is_active is True
