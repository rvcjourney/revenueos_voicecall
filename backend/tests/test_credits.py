"""
tests/test_credits.py — Credit-based call billing (app/core/credits.py),
plan-change proration (app/core/billing.py), and the SuperAdmin credit
management API (app/api/platform.py) tests.

1 credit = 1 minute of call time, rounded up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import app.workers.tasks.campaign as campaign_module
from app.core.billing import compute_blended_monthly_credits
from app.core.credits import (
    DEFAULT_CREDITS_PER_MONTH,
    has_credits_remaining,
    minutes_for_duration,
    record_call_credits,
    reset_credit_period_if_stale,
    resolve_org_credits_per_month,
)
from app.core.security import create_platform_token, hash_password
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallEvent, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.subscription import Subscription
from app.models.user import Organization


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _make_org(db, *, credits_per_month: int | None = None, credit_price_cents: int = 10) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    if credits_per_month is not None:
        plan = Plan(
            name=f"Plan-{uuid.uuid4().hex[:6]}",
            price_minor=1000,
            monthly_call_quota=1000,
            max_concurrent_calls=5,
            credits_per_month=credits_per_month,
            credit_price_cents=credit_price_cents,
        )
        db.add(plan)
        await db.flush()
        db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))

    await db.commit()
    await db.refresh(org)
    return org


# ── minutes_for_duration ───────────────────────────────────────────────────

def test_minutes_for_duration_rounds_up():
    assert minutes_for_duration(None) == 0
    assert minutes_for_duration(0) == 0
    assert minutes_for_duration(1) == 1
    assert minutes_for_duration(60) == 1
    assert minutes_for_duration(61) == 2
    assert minutes_for_duration(150) == 3


# ── record_call_credits: usage increment + excess billing ────────────────

async def test_record_call_credits_increments_usage(db):
    org = await _make_org(db, credits_per_month=100)

    result = await record_call_credits(db, org_id=org.id, duration_seconds=125)  # ceil(125/60) = 3
    await db.commit()

    assert result["minutes_billed"] == 3
    assert result["credits_used_this_period"] == 3
    assert result["overage_minutes"] == 0
    assert result["overage_cost_cents"] == 0

    await db.refresh(org)
    assert org.credits_used_this_period == 3


async def test_record_call_credits_bills_excess_over_allotment(db):
    org = await _make_org(db, credits_per_month=5, credit_price_cents=10)

    r1 = await record_call_credits(db, org_id=org.id, duration_seconds=300)  # 5 minutes — exactly at cap
    await db.commit()
    assert r1["overage_minutes"] == 0

    r2 = await record_call_credits(db, org_id=org.id, duration_seconds=180)  # 3 minutes — entirely over
    await db.commit()
    assert r2["minutes_billed"] == 3
    assert r2["overage_minutes"] == 3
    assert r2["overage_cost_cents"] == 30
    assert r2["credits_used_this_period"] == 8


async def test_record_call_credits_bills_only_the_overhanging_portion(db):
    org = await _make_org(db, credits_per_month=10, credit_price_cents=10)

    await record_call_credits(db, org_id=org.id, duration_seconds=480)  # 8 minutes, within cap
    await db.commit()

    # 5-minute call: usage goes 8 -> 13, but only 3 of those 5 minutes are over the cap of 10
    result = await record_call_credits(db, org_id=org.id, duration_seconds=300)
    await db.commit()
    assert result["minutes_billed"] == 5
    assert result["overage_minutes"] == 3
    assert result["overage_cost_cents"] == 30


async def test_record_call_credits_unknown_org_is_safe_noop(db):
    result = await record_call_credits(db, org_id=uuid.uuid4(), duration_seconds=120)
    assert result["minutes_billed"] == 2
    assert result["credits_used_this_period"] == 0


# ── has_credits_remaining: hard stop, no grace overage window ─────────────

async def test_has_credits_remaining_true_below_allotment(db):
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 99
    await db.commit()
    assert await has_credits_remaining(db, org.id) is True


async def test_has_credits_remaining_false_exactly_at_allotment(db):
    """Hard stop at 100% -- no 20% grace window past the limit."""
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 100
    await db.commit()
    assert await has_credits_remaining(db, org.id) is False


async def test_has_credits_remaining_false_when_over_allotment(db):
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 119  # previously still under the old 20% grace ceiling
    await db.commit()
    assert await has_credits_remaining(db, org.id) is False


# ── Monthly reset ──────────────────────────────────────────────────────────

async def test_reset_credit_period_if_stale_resets_after_30_days(db):
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 42
    org.last_credit_reset_at = _now() - timedelta(days=31)
    await db.commit()

    did_reset = await reset_credit_period_if_stale(db, org)
    await db.commit()

    assert did_reset is True
    assert org.credits_used_this_period == 0
    assert (_now() - org.last_credit_reset_at) < timedelta(minutes=1)


async def test_reset_credit_period_if_stale_noop_within_30_days(db):
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 42
    org.last_credit_reset_at = _now() - timedelta(days=10)
    await db.commit()

    did_reset = await reset_credit_period_if_stale(db, org)
    assert did_reset is False
    assert org.credits_used_this_period == 42


async def test_reset_clears_prorated_override(db):
    org = await _make_org(db, credits_per_month=100)
    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    sub.prorated_credits_override = 250
    org.last_credit_reset_at = _now() - timedelta(days=31)
    await db.commit()

    await reset_credit_period_if_stale(db, org)
    await db.commit()
    await db.refresh(sub)

    assert sub.prorated_credits_override is None


async def test_resolve_org_credits_per_month_uses_override_when_set(db):
    org = await _make_org(db, credits_per_month=100)
    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    sub.prorated_credits_override = 777
    await db.commit()

    assert await resolve_org_credits_per_month(db, org.id) == 777


async def test_resolve_org_credits_per_month_falls_back_to_default_without_subscription(db):
    org = await _make_org(db)  # no plan/subscription at all
    assert await resolve_org_credits_per_month(db, org.id) == DEFAULT_CREDITS_PER_MONTH


# ── Proration (app/core/billing.py) ───────────────────────────────────────

def test_compute_blended_monthly_credits_halfway_through_period():
    period_start = _now() - timedelta(days=15)
    blended = compute_blended_monthly_credits(
        old_plan_credits=500, new_plan_credits=2000, period_start=period_start, now=_now(),
    )
    assert 1200 <= blended <= 1300  # ~halfway between 500 and 2000


def test_compute_blended_monthly_credits_at_period_start_uses_new_plan_rate():
    now = _now()
    blended = compute_blended_monthly_credits(
        old_plan_credits=500, new_plan_credits=2000, period_start=now, now=now,
    )
    assert blended == 2000


def test_compute_blended_monthly_credits_at_period_end_uses_old_plan_rate():
    period_start = _now() - timedelta(days=30)
    blended = compute_blended_monthly_credits(
        old_plan_credits=500, new_plan_credits=2000, period_start=period_start, now=_now(),
    )
    assert blended == 500


async def test_patch_org_plan_change_sets_prorated_credits_override(client, db):
    admin = PlatformAdmin(
        email="super-credits@motmvoice.com", hashed_password=hash_password("pw-super-1"),
        full_name="Super Admin", is_active=True,
    )
    db.add(admin)
    await db.flush()

    org = await _make_org(db, credits_per_month=500)
    old_sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))

    new_plan = Plan(
        name="Premium-Test", price_minor=999900, monthly_call_quota=20000,
        max_concurrent_calls=20, credits_per_month=2000, credit_price_cents=8,
    )
    db.add(new_plan)
    await db.commit()

    token = create_platform_token(str(admin.id))
    resp = await client.patch(
        f"/api/platform/orgs/{org.id}",
        json={"plan_id": str(new_plan.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    await db.refresh(old_sub)
    assert old_sub.plan_id == new_plan.id
    # Changed essentially at the start of the (fresh) org's credit period —
    # blended value should sit very close to the new plan's full rate.
    assert old_sub.prorated_credits_override is not None
    assert 1900 <= old_sub.prorated_credits_override <= 2000


# ── SuperAdmin credit management API ──────────────────────────────────────

async def test_credit_adjust_endpoint_consumes_and_grants_credits(client, db):
    admin = PlatformAdmin(
        email="super-credits2@motmvoice.com", hashed_password=hash_password("pw-super-2"),
        full_name="Super Admin", is_active=True,
    )
    db.add(admin)
    await db.flush()
    org = await _make_org(db, credits_per_month=100)
    token = create_platform_token(str(admin.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/platform/orgs/{org.id}/credits/adjust",
        json={"delta": 20, "reason": "manual correction"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["credits_used_this_period"] == 20

    resp2 = await client.post(
        f"/api/platform/orgs/{org.id}/credits/adjust",
        json={"delta": -5, "reason": "goodwill credit"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["credits_used_this_period"] == 15


async def test_credit_adjust_endpoint_clamps_at_zero(client, db):
    admin = PlatformAdmin(
        email="super-credits3@motmvoice.com", hashed_password=hash_password("pw-super-3"),
        full_name="Super Admin", is_active=True,
    )
    db.add(admin)
    await db.flush()
    org = await _make_org(db, credits_per_month=100)
    token = create_platform_token(str(admin.id))

    resp = await client.post(
        f"/api/platform/orgs/{org.id}/credits/adjust",
        json={"delta": -1000, "reason": "huge bonus"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["credits_used_this_period"] == 0


async def test_credit_reset_endpoint_zeroes_usage(client, db):
    admin = PlatformAdmin(
        email="super-credits4@motmvoice.com", hashed_password=hash_password("pw-super-4"),
        full_name="Super Admin", is_active=True,
    )
    db.add(admin)
    await db.flush()
    org = await _make_org(db, credits_per_month=100)
    org.credits_used_this_period = 88
    await db.commit()
    token = create_platform_token(str(admin.id))

    resp = await client.post(
        f"/api/platform/orgs/{org.id}/credits/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["credits_used_this_period"] == 0

    await db.refresh(org)
    assert org.credits_used_this_period == 0
    assert (_now() - org.last_credit_reset_at) < timedelta(minutes=1)


# ── Campaign worker integration: _finalize bills credits ──────────────────

async def _make_call_setup(db, *, credits_per_month: int):
    org = await _make_org(db, credits_per_month=credits_per_month)

    agent = AgentTemplate(org_id=org.id, name="Credit Test Agent")
    db.add(agent)
    await db.flush()

    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Credit Test Campaign")
    db.add(campaign)
    await db.flush()

    contact = CampaignContact(
        campaign_id=campaign.id, org_id=org.id, name="Contact", phone="+911234567890",
        status=ContactStatus.DIALING,
    )
    db.add(contact)
    await db.flush()

    call = Call(
        org_id=org.id, campaign_id=campaign.id, contact_id=contact.id,
        livekit_room_name=f"credit-test-{contact.id.hex[:8]}",
        phone_number=contact.phone, direction=CallDirection.OUTBOUND,
        status=CallStatus.INITIATED,
        started_at=_now() - timedelta(minutes=4),  # ~4-minute call
    )
    db.add(call)
    await db.commit()
    await db.refresh(org)
    await db.refresh(campaign)
    await db.refresh(contact)
    await db.refresh(call)
    return org, campaign, contact, call


async def test_finalize_bills_credits_for_a_connected_call(db):
    org, campaign, contact, call = await _make_call_setup(db, credits_per_month=100)

    async with db.begin_nested():
        await campaign_module._finalize(
            db, call=call, contact=contact, campaign=campaign,
            place_result="placed", wait_result="done",
            # Production always passes answered_at when place_result=="placed"
            # (see _run_one_call) — it's the anchor _finalize uses to compute
            # duration_seconds. call.started_at was set ~4 minutes in the past
            # by _make_call_setup, giving the ~4-minute duration this test expects.
            answered_at=call.started_at,
        )

    await db.refresh(org)
    assert org.credits_used_this_period == 4  # ~4-minute call -> 4 credits
    assert call.status == CallStatus.COMPLETED


async def test_finalize_does_not_bill_credits_for_no_answer(db):
    org, campaign, contact, call = await _make_call_setup(db, credits_per_month=100)

    async with db.begin_nested():
        await campaign_module._finalize(
            db, call=call, contact=contact, campaign=campaign,
            place_result="no_answer", wait_result="skipped",
        )

    await db.refresh(org)
    assert org.credits_used_this_period == 0


async def test_finalize_writes_overage_call_event(db):
    org, campaign, contact, call = await _make_call_setup(db, credits_per_month=2)  # cap well below 4 min

    async with db.begin_nested():
        await campaign_module._finalize(
            db, call=call, contact=contact, campaign=campaign,
            place_result="placed", wait_result="done",
            answered_at=call.started_at,
        )

    events = (await db.execute(
        select(CallEvent).where(CallEvent.call_id == call.id, CallEvent.event_type == "credit_overage_billed")
    )).scalars().all()
    assert len(events) == 1
    assert events[0].payload["overage_minutes"] == 2  # 4 minutes billed, 2 credits allotted
