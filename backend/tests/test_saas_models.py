"""
tests/test_saas_models.py — Model-level tests for the new SaaS tables:
platform_admins, plans, subscriptions, audit_log.
Creates one row of each via the test session and asserts column defaults.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.platform_admin import PlatformAdmin
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization


@pytest.mark.asyncio
async def test_platform_admin_defaults(db):
    admin = PlatformAdmin(
        email="super@motmvoice.com",
        hashed_password="hashed",
        full_name="Super Admin",
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    assert admin.id is not None
    assert admin.is_active is True
    assert admin.last_login_at is None
    assert admin.created_at is not None


@pytest.mark.asyncio
async def test_plan_defaults(db):
    plan = Plan(
        name="Starter",
        price_minor=99900,
        monthly_call_quota=1000,
        max_concurrent_calls=5,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    assert plan.id is not None
    assert plan.currency == "INR"
    assert plan.features == {}
    assert plan.is_active is True


@pytest.mark.asyncio
async def test_subscription_defaults(db):
    org = Organization(name="Acme Inc", slug="acme-inc")
    db.add(org)
    await db.flush()

    plan = Plan(
        name="Growth",
        price_minor=499900,
        monthly_call_quota=10000,
        max_concurrent_calls=25,
    )
    db.add(plan)
    await db.flush()

    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        status="trialing",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    assert sub.id is not None
    assert sub.status == "trialing"
    assert sub.deleted_at is None
    assert sub.provider is None


@pytest.mark.asyncio
async def test_audit_log_defaults(db):
    entry = AuditLog(
        actor_type="system",
        action="campaign.launch",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    assert entry.id is not None
    assert entry.audit_metadata == {}
    assert entry.actor_id is None
    assert entry.org_id is None
    assert entry.created_at is not None

    fetched = await db.scalar(select(AuditLog).where(AuditLog.id == entry.id))
    assert fetched.action == "campaign.launch"
