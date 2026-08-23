"""
tests/test_inbound_calling.py — Inbound agent CRUD, self-serve inbound setup
on a connected number, and the agent-facing internal resolve/start endpoint.

Vobiz and LiveKit calls are always mocked -- these tests never touch the
network, mirroring test_vobiz_connect.py's conventions.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.config import settings
from app.core.security import create_access_token, hash_password, sign_webhook_payload
from app.models.call import Call, CallDirection, CallStatus
from app.models.inbound_agent import InboundAgentTemplate
from app.models.sip import SipTrunk, SipTransport
from app.models.user import Organization, User, UserRole

FREE_FEATURES = {"allowed_voice_providers": ["sarvam"], "voice_cloning": False}


async def _make_org_and_admin(db) -> tuple[Organization, User, str]:
    org = Organization(name="Acme Inc", slug="acme-inc")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email="admin@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Acme Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, user, token


async def _make_connected_trunk(db, org: Organization) -> SipTrunk:
    trunk = SipTrunk(
        org_id=org.id,
        name="Vobiz +912212345678",
        livekit_trunk_id="ST_outbound_abc",
        sip_domain="abc123.sip.vobiz.ai",
        sip_username="real_id",
        sip_password="super-secret-vobiz-token",
        caller_id="+912212345678",
        transport=SipTransport.TCP,
        is_default=True,
        is_active=True,
    )
    trunk.vobiz_auth_id = "real_id"
    trunk.vobiz_auth_token = "super-secret-vobiz-token"
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)
    return trunk


async def _make_inbound_agent(db, org: Organization) -> InboundAgentTemplate:
    agent = InboundAgentTemplate(
        org_id=org.id,
        name="Support Line",
        system_prompt="You are a support agent.",
        welcome_message="Namaste, how can I help?",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


def _fake_livekit_client(*, inbound_trunk_id: str = "ST_inbound_fake", dispatch_rule_id: str = "SDR_fake"):
    fake = MagicMock()
    fake.sip.create_inbound_trunk = AsyncMock(return_value=MagicMock(sip_trunk_id=inbound_trunk_id))
    fake.sip.create_dispatch_rule = AsyncMock(return_value=MagicMock(sip_dispatch_rule_id=dispatch_rule_id))
    fake.sip.delete_dispatch_rule = AsyncMock()
    fake.sip.delete_trunk = AsyncMock()
    fake.aclose = AsyncMock()
    return fake


# ── Inbound agent CRUD ──────────────────────────────────────────────────────

async def test_inbound_agent_crud_round_trip(client, db):
    _org, _user, token = await _make_org_and_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/inbound-agents",
        json={"name": "Support Line", "system_prompt": "Be helpful."},
        headers=headers,
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    list_resp = await client.get("/api/inbound-agents", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    update_resp = await client.patch(
        f"/api/inbound-agents/{agent_id}", json={"name": "Renamed Line"}, headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Renamed Line"

    del_resp = await client.delete(f"/api/inbound-agents/{agent_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp2 = await client.get("/api/inbound-agents", headers=headers)
    assert list_resp2.json()["total"] == 0


async def test_inbound_agent_rejects_disallowed_voice_provider(client, db):
    org = Organization(name="Free Org", slug="free-org")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email="admin@free.test", hashed_password=hash_password("pw-12345"),
        full_name="Free Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    from app.models.plan import Plan
    from app.models.subscription import Subscription
    plan = Plan(name="Free", price_minor=0, monthly_call_quota=100, max_concurrent_calls=1, features=FREE_FEATURES)
    db.add(plan)
    await db.flush()
    db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))
    await db.commit()

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    resp = await client.post(
        "/api/inbound-agents",
        json={"name": "Bot", "voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Self-serve inbound setup on a connected number ──────────────────────────

async def test_setup_inbound_calling_success(client, db, monkeypatch):
    org, _user, token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    monkeypatch.setattr(settings, "LIVEKIT_SIP_HOSTNAME", "sip.example.livekit.cloud")

    fake_lk = _fake_livekit_client()
    with patch(
        "app.api.sip_trunks.create_vobiz_inbound_trunk", new=AsyncMock(return_value="vobiz-trunk-123"),
    ) as mock_create, patch(
        "app.api.sip_trunks.assign_vobiz_number_to_trunk", new=AsyncMock(return_value=None),
    ) as mock_assign, patch("app.api.sip_trunks.LiveKitAPI", return_value=fake_lk):
        resp = await client.post(
            f"/api/sip-trunks/{trunk.id}/inbound",
            json={"inbound_agent_template_id": str(agent.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["inbound_enabled"] is True
    assert body["inbound_agent_template_id"] == str(agent.id)

    mock_create.assert_awaited_once()
    assert mock_create.call_args.kwargs["inbound_destination"] == "sip.example.livekit.cloud"
    mock_assign.assert_awaited_once()

    await db.refresh(trunk)
    assert trunk.inbound_enabled is True
    assert trunk.inbound_agent_template_id == agent.id
    assert trunk.vobiz_inbound_trunk_id == "vobiz-trunk-123"
    assert trunk.livekit_inbound_trunk_id == "ST_inbound_fake"
    assert trunk.livekit_inbound_dispatch_rule_id == "SDR_fake"

    # The dispatch rule's room metadata should be minimal, not the full prompt.
    dispatch_call = fake_lk.sip.create_dispatch_rule.call_args.args[0]
    room_meta = json.loads(dispatch_call.room_config.metadata)
    assert room_meta == {"call_type": "inbound", "sip_trunk_id": str(trunk.id)}
    assert dispatch_call.room_config.agents[0].agent_name == "voice-call-agent"


async def test_setup_inbound_calling_already_enabled_conflicts(client, db, monkeypatch):
    org, _user, token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    await db.commit()
    monkeypatch.setattr(settings, "LIVEKIT_SIP_HOSTNAME", "sip.example.livekit.cloud")

    resp = await client.post(
        f"/api/sip-trunks/{trunk.id}/inbound",
        json={"inbound_agent_template_id": str(agent.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_patch_inbound_agent_makes_no_external_calls(client, db):
    org, _user, token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent_a = await _make_inbound_agent(db, org)
    agent_b = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent_a.id
    await db.commit()

    # No Vobiz/LiveKit patches at all -- if the endpoint tried to call either,
    # this would hit the real network and fail/hang, so success here proves
    # it didn't.
    resp = await client.patch(
        f"/api/sip-trunks/{trunk.id}/inbound",
        json={"inbound_agent_template_id": str(agent_b.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["inbound_agent_template_id"] == str(agent_b.id)

    await db.refresh(trunk)
    assert trunk.inbound_agent_template_id == agent_b.id


async def test_teardown_inbound_calling(client, db):
    org, _user, token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    trunk.vobiz_inbound_trunk_id = "vobiz-trunk-123"
    trunk.livekit_inbound_trunk_id = "ST_inbound_fake"
    trunk.livekit_inbound_dispatch_rule_id = "SDR_fake"
    await db.commit()

    fake_lk = _fake_livekit_client()
    with patch("app.api.sip_trunks.unassign_vobiz_number", new=AsyncMock(return_value=None)) as mock_unassign, \
         patch("app.api.sip_trunks.LiveKitAPI", return_value=fake_lk):
        resp = await client.delete(
            f"/api/sip-trunks/{trunk.id}/inbound", headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["inbound_enabled"] is False
    mock_unassign.assert_awaited_once()
    fake_lk.sip.delete_dispatch_rule.assert_awaited_once()
    fake_lk.sip.delete_trunk.assert_awaited_once()

    await db.refresh(trunk)
    assert trunk.inbound_enabled is False
    assert trunk.inbound_agent_template_id is None
    assert trunk.vobiz_inbound_trunk_id is None
    assert trunk.livekit_inbound_trunk_id is None
    assert trunk.livekit_inbound_dispatch_rule_id is None


# ── Internal agent-facing resolve/start endpoint ────────────────────────────

async def test_internal_inbound_start_rejects_missing_signature(client, db):
    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    await db.commit()

    resp = await client.post(
        "/api/internal/inbound/start",
        json={"sip_trunk_id": str(trunk.id), "room_name": "inbound-x", "from_number": "+919876543210", "to_number": trunk.caller_id},
    )
    assert resp.status_code == 401


async def test_internal_inbound_start_creates_call_and_returns_config(client, db):
    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    await db.commit()

    payload = {
        "sip_trunk_id": str(trunk.id),
        "room_name": "inbound-9122-abcd1234",
        "from_number": "+919876543210",
        "to_number": trunk.caller_id,
    }
    body = json.dumps(payload).encode()
    signature = sign_webhook_payload(body)

    resp = await client.post(
        "/api/internal/inbound/start",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["system_prompt"] == agent.system_prompt
    assert out["welcome_message"] == agent.welcome_message
    call_id = out["call_id"]

    call = await db.get(Call, UUID(call_id))
    assert call is not None
    assert call.direction == CallDirection.INBOUND
    assert call.org_id == org.id
    assert call.sip_trunk_id == trunk.id
    assert call.phone_number == "+919876543210"


async def test_internal_inbound_start_rejects_when_no_credits_remaining(client, db):
    """Inbound calls must be gated by the org's credit balance the same way
    outbound test/campaign calls are — an org with none left shouldn't be
    able to accept a real (billable) inbound call."""
    from app.core.credits import DEFAULT_CREDITS_PER_MONTH

    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    org.credits_used_this_period = DEFAULT_CREDITS_PER_MONTH  # fully used, no active Subscription
    await db.commit()

    payload = {
        "sip_trunk_id": str(trunk.id), "room_name": "inbound-x",
        "from_number": "+919876543210", "to_number": trunk.caller_id,
    }
    body = json.dumps(payload).encode()
    resp = await client.post(
        "/api/internal/inbound/start",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)},
    )
    assert resp.status_code == 402

    from sqlalchemy import select as _select
    calls = (await db.execute(_select(Call).where(Call.org_id == org.id))).scalars().all()
    assert calls == []  # rejected before any Call row was created


async def test_internal_inbound_start_rejects_when_org_at_capacity(client, db, fake_redis):
    """A second concurrent inbound call must be rejected once the org's
    plan-based concurrency slot (same Redis mechanism outbound calls use) is
    already full, not accepted for free on top of it."""
    from app.core.concurrency import acquire_org_slot

    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)  # is_active=True -> 1 active trunk
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    await db.commit()

    # No Subscription -> DEFAULT_MAX_CONCURRENT_PER_ORG (1) * 1 active trunk = 1 slot total.
    assert await acquire_org_slot(org.id, 1) is True  # fill the org's only slot

    payload = {
        "sip_trunk_id": str(trunk.id), "room_name": "inbound-y",
        "from_number": "+919876543211", "to_number": trunk.caller_id,
    }
    body = json.dumps(payload).encode()
    resp = await client.post(
        "/api/internal/inbound/start",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)},
    )
    assert resp.status_code == 409


async def test_agent_report_finalizes_and_bills_inbound_call(client, db, fake_redis):
    """The finalize path added to agent_report for inbound calls: it should
    stamp ended_at/duration_seconds from answered_at, bill the org via
    record_call_credits (mirroring outbound's _finalize), mark the call
    COMPLETED, and release the org concurrency slot acquired at accept-time."""
    from app.core.concurrency import get_current_usage
    from app.core.security import sign_webhook_payload as _sign

    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    agent = await _make_inbound_agent(db, org)
    trunk.inbound_enabled = True
    trunk.inbound_agent_template_id = agent.id
    await db.commit()

    start_payload = {
        "sip_trunk_id": str(trunk.id), "room_name": "inbound-bill",
        "from_number": "+919876543212", "to_number": trunk.caller_id,
    }
    start_body = json.dumps(start_payload).encode()
    start_resp = await client.post(
        "/api/internal/inbound/start",
        content=start_body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": _sign(start_body)},
    )
    assert start_resp.status_code == 200
    call_id = start_resp.json()["call_id"]

    usage_mid_call = await get_current_usage(db, org.id)
    assert usage_mid_call["in_use"] == 1  # slot held for the duration of the call

    # Push answered_at back 90s so duration/billing math has a known, nonzero value.
    from datetime import timedelta
    call_row = await db.get(Call, UUID(call_id))
    call_row.answered_at = call_row.answered_at - timedelta(seconds=90)
    await db.commit()

    report_payload = {"outcome": "interested", "summary": "Asked about pricing.", "transcript": []}
    report_body = json.dumps(report_payload).encode()
    import app.workers.tasks.campaign as campaign_module
    with patch.object(campaign_module.fetch_recording_for_inbound_call, "apply_async", MagicMock()):
        report_resp = await client.post(
            f"/api/calls/{call_id}/agent-report",
            content=report_body,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": _sign(report_body)},
        )
    assert report_resp.status_code == 204

    await db.refresh(call_row)
    assert call_row.status == CallStatus.COMPLETED
    assert call_row.ended_at is not None
    assert call_row.duration_seconds is not None and call_row.duration_seconds >= 90

    await db.refresh(org)
    assert org.credits_used_this_period == 2  # ceil(90s / 60) = 2 minutes billed

    usage_after = await get_current_usage(db, org.id)
    assert usage_after["in_use"] == 0  # org slot released


async def test_internal_inbound_start_404_when_not_configured(client, db):
    org, _user, _token = await _make_org_and_admin(db)
    trunk = await _make_connected_trunk(db, org)
    # inbound_enabled left False

    payload = {
        "sip_trunk_id": str(trunk.id),
        "room_name": "inbound-x",
        "from_number": "+919876543210",
        "to_number": trunk.caller_id,
    }
    body = json.dumps(payload).encode()
    signature = sign_webhook_payload(body)

    resp = await client.post(
        "/api/internal/inbound/start",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
    )
    assert resp.status_code == 404
