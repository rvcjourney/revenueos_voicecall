"""
tests/test_concurrency.py — Per-org (plan-based) and per-trunk concurrency tests.

Uses the `fake_redis` fixture (conftest.py) for the Redis-backed slot/queue
primitives, and the local Postgres test DB (`db` fixture) for plan resolution
and the full _run_one_call dispatcher path. LiveKit is mocked — these tests
never touch the network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

import app.workers.tasks.campaign as campaign_module
from app.core.concurrency import (
    DEFAULT_MAX_CONCURRENT_PER_ORG,
    acquire_org_slot,
    org_slot_key,
    release_org_slot,
    resolve_org_max_concurrent,
)
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.agent import AgentTemplate
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization


# ── Primitive-level tests (fakeredis only, no DB) ─────────────────────────────

async def test_acquire_org_slot_succeeds_under_cap(fake_redis):
    org_id = uuid.uuid4()
    assert await acquire_org_slot(org_id, 2) is True
    assert await acquire_org_slot(org_id, 2) is True


async def test_acquire_org_slot_fails_at_cap(fake_redis):
    org_id = uuid.uuid4()
    assert await acquire_org_slot(org_id, 2) is True
    assert await acquire_org_slot(org_id, 2) is True
    # Third attempt: org is at its cap — caller should queue, not dial
    assert await acquire_org_slot(org_id, 2) is False


async def test_release_org_slot_frees_capacity(fake_redis):
    org_id = uuid.uuid4()
    assert await acquire_org_slot(org_id, 1) is True
    assert await acquire_org_slot(org_id, 1) is False

    await release_org_slot(org_id)

    assert await acquire_org_slot(org_id, 1) is True


async def test_trunk_and_org_limits_enforced_independently(fake_redis):
    trunk_id = "ST_independent_test"
    org_id = uuid.uuid4()

    # Exhaust the trunk's slots entirely
    for _ in range(campaign_module._MAX_CONCURRENT_PER_TRUNK):
        assert await campaign_module._acquire_trunk_slot(trunk_id) is True
    assert await campaign_module._acquire_trunk_slot(trunk_id) is False  # trunk now full

    # The org slot must be completely unaffected by trunk exhaustion
    assert await acquire_org_slot(org_id, 5) is True

    # And exhausting the org slot must not affect the (already-full) trunk
    org_id2 = uuid.uuid4()
    assert await acquire_org_slot(org_id2, 1) is True
    assert await acquire_org_slot(org_id2, 1) is False
    assert await campaign_module._acquire_trunk_slot(trunk_id) is False  # still full, unrelated


# ── Plan resolution (DB-backed) ───────────────────────────────────────────────

async def test_resolve_org_max_concurrent_from_active_plan(db, fake_redis):
    org = Organization(name="Plan Org", slug="plan-org")
    db.add(org)
    await db.flush()

    plan = Plan(name="Growth", price_minor=499900, monthly_call_quota=10000, max_concurrent_calls=7)
    db.add(plan)
    await db.flush()

    db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))
    await db.commit()

    assert await resolve_org_max_concurrent(db, org.id) == 7


async def test_resolve_org_max_concurrent_falls_back_to_default_without_plan(db, fake_redis):
    org = Organization(name="No Plan Org", slug="no-plan-org")
    db.add(org)
    await db.commit()

    assert await resolve_org_max_concurrent(db, org.id) == DEFAULT_MAX_CONCURRENT_PER_ORG


# ── Usage endpoint ─────────────────────────────────────────────────────────────

async def test_usage_endpoint_reports_in_use_max_queued(client, db, fake_redis):
    from app.core.security import create_access_token, hash_password
    from app.models.user import User, UserRole

    org = Organization(name="Usage Org", slug="usage-org")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email="usage@acme.test", hashed_password=hash_password("pw-123456"),
        full_name="Usage User", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    await acquire_org_slot(org.id, DEFAULT_MAX_CONCURRENT_PER_ORG)  # simulate 1 active call

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    resp = await client.get("/api/usage/concurrency", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["in_use"] == 1
    assert body["max"] == DEFAULT_MAX_CONCURRENT_PER_ORG
    assert body["queued"] == 0


# ── Full dispatcher path (_run_one_call) — real DB rows, mocked LiveKit ───────

async def _make_campaign_setup(db):
    org = Organization(name="Dispatch Org", slug=f"dispatch-org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    agent = AgentTemplate(org_id=org.id, name="Test Agent")
    db.add(agent)
    await db.flush()

    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Test Campaign")
    db.add(campaign)
    await db.flush()

    contact = CampaignContact(
        campaign_id=campaign.id,
        org_id=org.id,
        name="Test Contact",
        phone="+911234567890",
        status=ContactStatus.DIALING,  # dispatcher already marked it DIALING before calling _run_one_call
    )
    db.add(contact)
    await db.flush()

    call = Call(
        org_id=org.id,
        campaign_id=campaign.id,
        contact_id=contact.id,
        livekit_room_name=f"test-room-{contact.id.hex[:8]}",
        phone_number=contact.phone,
        direction=CallDirection.OUTBOUND,
        status=CallStatus.INITIATED,
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.commit()
    await db.refresh(org)
    await db.refresh(campaign)
    await db.refresh(contact)
    await db.refresh(call)
    return org, campaign, contact, call


def _run_one_call_kwargs(campaign, contact, call, *, org_max_concurrent: int) -> dict:
    return dict(
        http=MagicMock(),
        campaign_id=str(campaign.id),
        org_id=campaign.org_id,
        agent_template_id=campaign.agent_template_id,
        call_id=call.id,
        contact_id=contact.id,
        contact_phone=contact.phone,
        contact_name=contact.name,
        room_name=call.livekit_room_name,
        livekit_trunk_id="ST_test_trunk",
        sip_caller_id="+910000000000",
        max_duration=600,
        system_prompt="", welcome_message="", voice_id="", voice_provider="elevenlabs",
        language="hinglish", llm_model="", llm_temperature=0.7,
        org_max_concurrent=org_max_concurrent,
    )


async def test_dial_proceeds_and_releases_slot_when_org_under_cap(db, fake_redis, monkeypatch):
    org, campaign, contact, call = await _make_campaign_setup(db)

    monkeypatch.setattr(campaign_module, "_place_call", AsyncMock(return_value="placed"))
    monkeypatch.setattr(campaign_module, "_wait_for_room_empty", AsyncMock(return_value="done"))
    monkeypatch.setattr(campaign_module, "_acquire_cps_slot", AsyncMock(return_value=None))
    # Prevent the fire-and-forget recording fetch from firing with real .env
    # Vobiz credentials (pytest only overrides specific settings, not these).
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_ID", "")
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_TOKEN", "")

    await campaign_module._run_one_call(
        **_run_one_call_kwargs(campaign, contact, call, org_max_concurrent=5)
    )

    await db.refresh(contact)
    await db.refresh(call)
    assert contact.status == ContactStatus.COMPLETED
    assert call.status == CallStatus.COMPLETED

    # Slot must be released once the call ends — capacity is free again
    remaining = await fake_redis.get(org_slot_key(org.id))
    assert (int(remaining) if remaining else 0) == 0


async def test_queued_contact_past_max_wait_marked_queue_timeout(db, fake_redis, monkeypatch):
    org, campaign, contact, call = await _make_campaign_setup(db)

    # Fill the org's only slot so _run_one_call can never acquire one
    assert await acquire_org_slot(org.id, 1) is True

    monkeypatch.setattr(campaign_module.settings, "CONCURRENCY_MAX_WAIT_SECONDS", 1)
    monkeypatch.setattr(campaign_module.asyncio, "sleep", AsyncMock(return_value=None))
    place_call_mock = AsyncMock()
    monkeypatch.setattr(campaign_module, "_place_call", place_call_mock)

    await campaign_module._run_one_call(
        **_run_one_call_kwargs(campaign, contact, call, org_max_concurrent=1)
    )

    await db.refresh(contact)
    assert contact.status == ContactStatus.QUEUE_TIMEOUT
    place_call_mock.assert_not_called()  # never dialed

    # The pre-created Call row must be cleaned up — the call was never placed.
    # db.get() would return the stale identity-mapped object without hitting
    # the DB (the delete happened on a different session/connection), so
    # issue a real SELECT instead.
    deleted_call = await db.scalar(select(Call).where(Call.id == call.id))
    assert deleted_call is None

    # The org's slot count is unaffected by a contact that never acquired one
    remaining = await fake_redis.get(org_slot_key(org.id))
    assert int(remaining) == 1
