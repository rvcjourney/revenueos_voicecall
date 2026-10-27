"""
tests/test_premium_features.py — Plan-gated voice cloning (app/core/plan_features.py,
app/api/voice_cloning.py) and the campaign dispatcher's use of the resulting
voice and the agent's filled-in placeholders.

Sarvam and LiveKit are always mocked — these tests never touch the network.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

import app.workers.tasks.campaign as campaign_module
from app.core.plan_features import MAX_CLONED_VOICES_PER_ORG
from app.core.security import create_access_token, create_platform_token, hash_password
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.cloned_voice import ClonedVoice
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.subscription import Subscription
from app.models.user import Organization, User, UserRole
from app.models.voice_clone_request import VoiceCloneRequest


async def _make_org_and_admin(db, *, plan_features: dict | None = None, cloning_allowed: bool = True) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}",
                       sarvam_cloning_allowed=cloning_allowed)
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


async def _make_platform_admin(db) -> tuple[PlatformAdmin, str]:
    admin = PlatformAdmin(
        email=f"super-{uuid.uuid4().hex[:8]}@motmvoice.test",
        hashed_password=hash_password("super-pw-123"),
        full_name="Super Admin",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin, create_platform_token(str(admin.id))


def _fake_storage() -> MagicMock:
    """Stand-in for app.storage.backend.get_storage() -- no real MinIO in tests."""
    storage = MagicMock()
    storage.upload = AsyncMock(return_value="fake-key")
    storage.download = AsyncMock(return_value=b"fake-audio-bytes")
    storage.delete = AsyncMock(return_value=None)
    storage.presigned_url = AsyncMock(return_value="https://example.test/fake-presigned-url")
    return storage


PRO_FEATURES = {"voice_cloning": False}
PREMIUM_FEATURES = {"voice_cloning": True}


async def _submit_voice_clone(client, token, name: str = "My Voice"):
    with patch("app.api.voice_cloning.get_storage", return_value=_fake_storage()):
        return await client.post(
            "/api/voice-cloning",
            data={"name": name, "language": "hindi"},
            files={
                "file": ("sample.mp3", b"fake-audio-bytes", "audio/mpeg"),
                "consent_video": ("consent.webm", b"fake-video-bytes", "video/webm"),
            },
            headers={"Authorization": f"Bearer {token}"},
        )


# ── Voice cloning API (submission → superadmin approval/rejection) ─────────

async def test_voice_cloning_rejected_on_pro_plan(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=PRO_FEATURES)
    assert (await _submit_voice_clone(client, token)).status_code == 403


async def test_voice_cloning_submission_creates_pending_request(client, db):
    """Submitting never calls the voice provider -- it sits as pending until a
    platform superadmin reviews the consent video."""
    org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)

    resp = await _submit_voice_clone(client, token)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["voice_id"] is None

    req = await db.scalar(select(VoiceCloneRequest).where(VoiceCloneRequest.org_id == org.id))
    assert (req.status, req.name, req.provider) == ("pending", "My Voice", "sarvam")
    # Not usable anywhere yet -- no ClonedVoice row exists until approval
    assert await db.scalar(select(ClonedVoice).where(ClonedVoice.org_id == org.id)) is None


async def test_voice_cloning_capped_per_org(client, db):
    """At most MAX_CLONED_VOICES_PER_ORG voices, counting pending requests;
    deleting one frees a slot."""
    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)

    request_ids = []
    for i in range(MAX_CLONED_VOICES_PER_ORG):
        resp = await _submit_voice_clone(client, token, f"Voice {i}")
        assert resp.status_code == 201
        request_ids.append(resp.json()["id"])

    assert (await _submit_voice_clone(client, token, "One too many")).status_code == 409

    with patch("app.api.voice_cloning.get_storage", return_value=_fake_storage()):
        del_resp = await client.delete(
            f"/api/voice-cloning/{request_ids[0]}", headers={"Authorization": f"Bearer {token}"}
        )
    assert del_resp.status_code == 204
    assert (await _submit_voice_clone(client, token, "A different voice")).status_code == 201


async def test_voice_clone_request_rejection_shows_reason_to_org_admin(client, db):
    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    _admin, admin_token = await _make_platform_admin(db)
    request_id = (await _submit_voice_clone(client, token)).json()["id"]

    reject_resp = await client.post(
        f"/api/platform/voice-clone-requests/{request_id}/reject",
        json={"reason": "Video doesn't clearly show the person's face"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    items = (await client.get("/api/voice-cloning", headers={"Authorization": f"Bearer {token}"})).json()["items"]
    assert [(i["status"], i["rejection_reason"]) for i in items] == [
        ("rejected", "Video doesn't clearly show the person's face")]


async def test_old_elevenlabs_voices_are_hidden_and_not_counted(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    for i in range(MAX_CLONED_VOICES_PER_ORG):
        db.add(ClonedVoice(org_id=org.id, created_by_id=user.id, name=f"Old {i}",
                           elevenlabs_voice_id=f"el-{i}", provider="elevenlabs"))
    await db.commit()

    assert (await client.get("/api/voice-cloning", headers={"Authorization": f"Bearer {token}"})).json()["items"] == []
    assert (await _submit_voice_clone(client, token)).status_code == 201


# ── Using a cloned voice on an agent template ─────────────────────────────

def _sarvam_clone(org_id, user_id, voice_id: str) -> ClonedVoice:
    return ClonedVoice(org_id=org_id, created_by_id=user_id, name="Voice A",
                       elevenlabs_voice_id=voice_id, provider="sarvam", language="hindi")


async def test_agent_can_use_own_orgs_cloned_voice_on_premium_plan(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    db.add(_sarvam_clone(org.id, user.id, "svc-mine"))
    await db.commit()

    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "language": "hindi", "voice_id": "svc-mine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["voice_id"] == "svc-mine"


async def test_agent_cannot_use_another_orgs_cloned_voice(client, db):
    other_org, other_user, _ = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    db.add(_sarvam_clone(other_org.id, other_user.id, "svc-theirs"))
    await db.commit()

    _org, _user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "language": "hindi", "voice_id": "svc-theirs"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_agent_cannot_use_cloned_voice_after_downgrade_from_premium(client, db):
    org, user, token = await _make_org_and_admin(db, plan_features=PRO_FEATURES)
    db.add(_sarvam_clone(org.id, user.id, "svc-mine"))
    await db.commit()

    resp = await client.post(
        "/api/agents",
        json={"name": "Bot", "language": "hindi", "voice_id": "svc-mine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_agent_rejects_a_voice_that_does_not_exist_in_its_language(client, db):
    _org, _user, token = await _make_org_and_admin(db)
    h = {"Authorization": f"Bearer {token}"}
    bad = await client.post("/api/agents", json={"name": "Bot", "language": "hindi", "voice_id": "9BWtsMINqrJLrRacOk9x"}, headers=h)
    assert bad.status_code == 422
    ok = await client.post("/api/agents", json={"name": "Bot", "language": "hindi", "voice_id": "ritu_hi_conversation"}, headers=h)
    assert ok.status_code == 201


# ── Campaign dispatcher: voice + filled placeholders flow through to _place_call ──

async def test_campaign_dispatch_sends_cloned_voice_and_filled_placeholders(db, fake_redis, monkeypatch):
    org = Organization(name=f"Dispatch Org {uuid.uuid4().hex[:6]}", slug=f"dispatch-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    plan = Plan(name=f"Plan-{uuid.uuid4().hex[:6]}", price_minor=1000, monthly_call_quota=1000,
                max_concurrent_calls=5, credits_per_month=100, features=PREMIUM_FEATURES)
    db.add(plan)
    await db.flush()
    db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))
    db.add(_sarvam_clone(org.id, None, "svc-cloned-premium"))
    agent = AgentTemplate(org_id=org.id, name="Ananya", language="hindi", voice_id="svc-cloned-premium",
                          welcome_message="Hi {userName}, this is Ananya from {partnerName}.",
                          system_prompt="Talk to {userName} at {companyName}.",
                          variables={"partnerName": "Acme", "userName": "there"})
    db.add(agent)
    await db.flush()
    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Premium Voice Campaign")
    db.add(campaign)
    await db.flush()
    contact = CampaignContact(campaign_id=campaign.id, org_id=org.id, name="Ravi", phone="+911234567890",
                              custom_fields={"username": "Ravi", "company_name": "Bharat Steel"},
                              status=ContactStatus.DIALING)
    db.add(contact)
    await db.flush()
    call = Call(org_id=org.id, campaign_id=campaign.id, contact_id=contact.id,
                livekit_room_name=f"cloned-voice-{contact.id.hex[:8]}",
                phone_number=contact.phone, direction=CallDirection.OUTBOUND, status=CallStatus.INITIATED,
                # Backdated so the near-instant mocked call still bills (see assertion below).
                started_at=datetime.now(timezone.utc) - timedelta(minutes=4))
    db.add(call)
    await db.commit()

    place_call_mock = AsyncMock(return_value="placed")
    monkeypatch.setattr(campaign_module, "_place_call", place_call_mock)

    # _finalize bills from the real wall-clock gap after answered_at; an instant
    # mock leaves ~0 s, so take just over a second.
    async def _wait_then_done(*args, **kwargs):
        await asyncio.sleep(1.1)
        return "done"

    monkeypatch.setattr(campaign_module, "_wait_for_room_empty", _wait_then_done)
    monkeypatch.setattr(campaign_module, "_acquire_cps_slot", AsyncMock(return_value=None))
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_ID", "")
    monkeypatch.setattr(campaign_module.settings, "VOBIZ_AUTH_TOKEN", "")

    from app.core import agent_variables, pipelines
    welcome, prompt, _ = agent_variables.render(
        agent.welcome_message, agent.system_prompt,
        columns=agent_variables.contact_columns(contact), defaults=agent.variables)
    assert welcome == "Hi Ravi, this is Ananya from Acme." and prompt == "Talk to Ravi at Bharat Steel."
    extra_meta = await pipelines.call_meta(db, org_id=org.id, language="hindi", voice_id=agent.voice_id)

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
        system_prompt=prompt, welcome_message=welcome, llm_temperature=0.7, speech_pace=1.0,
        extra_meta=extra_meta,
        org_max_concurrent=5,
    )

    place_call_mock.assert_awaited_once()
    _, kwargs = place_call_mock.call_args
    assert kwargs["welcome_message"] == "Hi Ravi, this is Ananya from Acme."
    sarvam = kwargs["extra_meta"]["sarvam"]
    assert (sarvam["voice_id"], sarvam["cloned"], sarvam["language"]) == ("svc-cloned-premium", True, "hindi")

    await db.refresh(org)
    assert org.credits_used_this_period > 0  # the call was billed too
