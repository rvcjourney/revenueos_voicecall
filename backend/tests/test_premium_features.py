"""
tests/test_premium_features.py — Plan-based voice feature gating
(app/core/plan_features.py), voice cloning (app/api/voice_cloning.py), and
the campaign dispatcher's use of the resulting voice_id/voice_provider.

ElevenLabs and LiveKit are always mocked — these tests never touch the network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

import app.workers.tasks.campaign as campaign_module
from app.core.elevenlabs_voice import ElevenLabsVoiceError
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentTemplate, VoiceProvider
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.cloned_voice import ClonedVoice
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization, User, UserRole


async def _make_org_and_admin(db, *, plan_features: dict | None = None) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    if plan_features is not None:
        plan = Plan(
            name=f"Plan-{uuid.uuid4().hex[:6]}", price_minor=1000, monthly_call_quota=1000,
            max_concurrent_calls=5, features=plan_features,
        )
        db.add(plan)
        await db.flush()
        db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))

    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Acme Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, user, token


FREE_FEATURES = {"allowed_voice_providers": ["sarvam"], "voice_cloning": False}
PRO_FEATURES = {"allowed_voice_providers": ["sarvam", "cartesia"], "voice_cloning": False}
PREMIUM_FEATURES = {
    "allowed_voice_providers": ["sarvam", "cartesia", "elevenlabs"],
    "voice_cloning": True,
}


# ── Agent template create/update gating ───────────────────────────────────

async def test_create_agent_rejects_elevenlabs_on_free_plan(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=FREE_FEATURES)

    resp = await client.post(
        "/api/agents",
        json={"name": "Sales Bot", "voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_create_agent_allows_sarvam_on_free_plan(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=FREE_FEATURES)

    resp = await client.post(
        "/api/agents",
        json={"name": "Sales Bot", "voice_provider": "sarvam"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["voice_provider"] == "sarvam"


async def test_create_agent_allows_elevenlabs_on_premium_plan(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)

    resp = await client.post(
        "/api/agents",
        json={"name": "Sales Bot", "voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


async def test_create_agent_unrestricted_without_subscription(client, db):
    """Orgs that predate the plan-gating scheme (no active subscription) are unrestricted."""
    _org, _user, token = await _make_org_and_admin(db, plan_features=None)

    resp = await client.post(
        "/api/agents",
        json={"name": "Sales Bot", "voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


async def test_update_agent_rejects_switching_to_disallowed_provider(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PRO_FEATURES)
    agent = AgentTemplate(org_id=org.id, created_by_id=user.id, name="Bot", voice_provider=VoiceProvider.SARVAM)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    resp = await client.patch(
        f"/api/agents/{agent.id}",
        json={"voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    await db.refresh(agent)
    assert agent.voice_provider == VoiceProvider.SARVAM  # unchanged


async def test_create_agent_rejects_elevenlabs_when_org_flag_disabled(client, db):
    org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    org.elevenlabs_enabled = False
    await db.commit()

    resp = await client.post(
        "/api/agents",
        json={"name": "Sales Bot", "voice_provider": "elevenlabs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Voice cloning API ──────────────────────────────────────────────────────

async def test_voice_cloning_rejected_on_pro_plan(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=PRO_FEATURES)

    resp = await client.post(
        "/api/voice-cloning",
        data={"name": "My Voice"},
        files={"file": ("sample.mp3", b"fake-audio-bytes", "audio/mpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_voice_cloning_creates_model_on_premium_plan(client, db):
    org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)

    with patch(
        "app.api.voice_cloning.clone_voice",
        new=AsyncMock(return_value="elevenlabs-voice-xyz"),
    ):
        resp = await client.post(
            "/api/voice-cloning",
            data={"name": "My Voice"},
            files={"file": ("sample.mp3", b"fake-audio-bytes", "audio/mpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["elevenlabs_voice_id"] == "elevenlabs-voice-xyz"
    assert body["status"] == "ready"

    cloned = await db.scalar(select(ClonedVoice).where(ClonedVoice.org_id == org.id))
    assert cloned is not None
    assert cloned.elevenlabs_voice_id == "elevenlabs-voice-xyz"


async def test_voice_cloning_elevenlabs_rejection_returns_400(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)

    with patch(
        "app.api.voice_cloning.clone_voice",
        new=AsyncMock(side_effect=ElevenLabsVoiceError("ElevenLabs rejected the sample")),
    ):
        resp = await client.post(
            "/api/voice-cloning",
            data={"name": "My Voice"},
            files={"file": ("sample.mp3", b"fake-audio-bytes", "audio/mpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400


async def test_voice_cloning_list_and_delete(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    cloned = ClonedVoice(org_id=org.id, created_by_id=user.id, name="Voice A", elevenlabs_voice_id="v-1")
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)

    list_resp = await client.get("/api/voice-cloning", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1

    with patch("app.api.voice_cloning.delete_voice", new=AsyncMock(return_value=None)):
        del_resp = await client.delete(
            f"/api/voice-cloning/{cloned.id}", headers={"Authorization": f"Bearer {token}"}
        )
    assert del_resp.status_code == 204

    await db.refresh(cloned)
    assert cloned.deleted_at is not None

    list_resp2 = await client.get("/api/voice-cloning", headers={"Authorization": f"Bearer {token}"})
    assert list_resp2.json()["items"] == []


# ── Using a cloned voice on an agent template ─────────────────────────────

async def test_agent_can_use_own_orgs_cloned_voice_on_premium_plan(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    cloned = ClonedVoice(org_id=org.id, created_by_id=user.id, name="Voice A", elevenlabs_voice_id="v-mine")
    db.add(cloned)
    await db.commit()

    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "voice_provider": "elevenlabs", "voice_id": "v-mine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["voice_id"] == "v-mine"


async def test_agent_cannot_use_another_orgs_cloned_voice(client, db):
    other_org, other_user, _ = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    cloned = ClonedVoice(org_id=other_org.id, created_by_id=other_user.id, name="Voice A", elevenlabs_voice_id="v-theirs")
    db.add(cloned)
    await db.commit()

    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "voice_provider": "elevenlabs", "voice_id": "v-theirs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_agent_cannot_use_cloned_voice_after_downgrade_from_premium(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PRO_FEATURES)
    cloned = ClonedVoice(org_id=org.id, created_by_id=user.id, name="Voice A", elevenlabs_voice_id="v-mine")
    db.add(cloned)
    await db.commit()

    # Pro plan doesn't allow elevenlabs at all, so this is rejected at the
    # provider-allowlist check before cloning is even considered.
    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "voice_provider": "elevenlabs", "voice_id": "v-mine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Campaign dispatcher: cloned voice flows through to _place_call ────────

async def _make_campaign_setup_with_voice(db, *, voice_provider: str, voice_id: str, plan_features: dict):
    org = Organization(name=f"Dispatch Org {uuid.uuid4().hex[:6]}", slug=f"dispatch-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    plan = Plan(
        name=f"Plan-{uuid.uuid4().hex[:6]}", price_minor=1000, monthly_call_quota=1000,
        max_concurrent_calls=5, credits_per_month=100, features=plan_features,
    )
    db.add(plan)
    await db.flush()
    db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))

    agent = AgentTemplate(
        org_id=org.id, name="Premium Voice Agent",
        voice_provider=voice_provider, voice_id=voice_id,
    )
    db.add(agent)
    await db.flush()

    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Premium Voice Campaign")
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
        livekit_room_name=f"cloned-voice-{contact.id.hex[:8]}",
        phone_number=contact.phone, direction=CallDirection.OUTBOUND,
        status=CallStatus.INITIATED,
        # Backdated so the dispatcher's near-instant mocked call flow still
        # produces a non-zero billable duration (see credit assertion below).
        started_at=datetime.now(timezone.utc) - timedelta(minutes=4),
    )
    db.add(call)
    await db.commit()
    await db.refresh(org)
    await db.refresh(campaign)
    await db.refresh(contact)
    await db.refresh(call)
    await db.refresh(agent)
    return org, campaign, contact, call, agent


async def test_campaign_dispatch_uses_cloned_voice_id_and_elevenlabs_provider(db, fake_redis, monkeypatch):
    org, campaign, contact, call, agent = await _make_campaign_setup_with_voice(
        db, voice_provider="elevenlabs", voice_id="v-cloned-premium", plan_features=PREMIUM_FEATURES,
    )

    place_call_mock = AsyncMock(return_value="placed")
    monkeypatch.setattr(campaign_module, "_place_call", place_call_mock)
    monkeypatch.setattr(campaign_module, "_wait_for_room_empty", AsyncMock(return_value="done"))
    monkeypatch.setattr(campaign_module, "_acquire_cps_slot", AsyncMock(return_value=None))
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_ID", "")
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_TOKEN", "")

    await campaign_module._run_one_call(
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
        system_prompt="", welcome_message="", voice_id=agent.voice_id,
        voice_provider=agent.voice_provider, language="hinglish",
        llm_model="", llm_temperature=0.7,
        org_max_concurrent=5,
    )

    place_call_mock.assert_awaited_once()
    _, kwargs = place_call_mock.call_args
    assert kwargs["voice_provider"] == "elevenlabs"
    assert kwargs["voice_id"] == "v-cloned-premium"

    await db.refresh(org)
    assert org.credits_used_this_period > 0  # the call was billed too
