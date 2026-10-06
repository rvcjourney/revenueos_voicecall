"""
tests/test_revenueos_launch.py — RevenueOS Brain integration (app/api/revenueos.py).

Vobiz, LiveKit and the Celery dispatch are always mocked: nothing here can
place a call. The database is the real test Postgres from conftest.py.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.core.credits import has_credits_remaining
from app.core.security import verify_password
from app.core.vobiz import VobizAuthError
from app.models.agent import AgentTemplate
from app.models.call import Call, CallOutcome, CallStatus, CallTranscript
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.company_profile import OrgCompanyProfile
from app.models.dnc import SystemDncEntry
from app.models.revenueos import RevenueOSClient, RevenueOSLaunch
from app.models.sip import SipTrunk
from app.models.user import Organization, User

KEY = "revenueos-test-key-that-is-at-least-32-chars"
HEADERS = {"X-RevenueOS-Key": KEY}
LAUNCH = "/api/integrations/revenueos/launch"
VOBIZ_TOKEN = "super-secret-vobiz-token"
PASSWORD = "client-password-123"


def _payload(**overrides) -> dict:
    body = {
        "client_reference": "client-acme",
        "reference": "acme-campaign-1",
        "user": {
            "email": "owner@acme-traders.example.com",
            "password": PASSWORD,
            "full_name": "Acme Owner",
            "company_name": "Acme Traders",
        },
        "phone_number": {"auth_id": "MA_ACME", "auth_token": VOBIZ_TOKEN, "did": "+912212345678"},
        "company_profile": {"company_name": "Acme Traders", "what_we_offer": "Wholesale packaging"},
        "agent": {"name": "Riya", "language": "hinglish", "system_prompt": "You are Riya from Acme."},
        "campaign": {"name": "October outreach"},
        "contacts": [
            {"name": "Asha", "phone": "+919000000001", "company": "Asha Foods", "website": "ashafoods.example"},
            {"name": "Vikram", "phone": "9000000002"},
        ],
    }
    body.update(overrides)
    return copy.deepcopy(body)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "REVENUEOS_API_KEY", KEY)
    monkeypatch.setattr(settings, "REVENUEOS_LAUNCH_ENABLED", True)
    monkeypatch.setattr(settings, "REVENUEOS_AUTO_START_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://test.example.com")


@contextmanager
def _outside_world(*, vobiz_error: Exception | None = None):
    """Mock everything that would leave the process. Yields (livekit, dispatch) mocks."""
    lk = MagicMock()
    lk.sip.create_outbound_trunk = AsyncMock(
        side_effect=lambda *_a, **_k: MagicMock(sip_trunk_id=f"ST_{lk.sip.create_outbound_trunk.await_count}")
    )
    lk.aclose = AsyncMock()
    dispatch = MagicMock()
    validate = AsyncMock(side_effect=vobiz_error) if vobiz_error else AsyncMock(return_value=None)
    with patch("app.api.sip_trunks.validate_vobiz_account_and_did", new=validate), \
         patch("app.api.sip_trunks.create_vobiz_outbound_trunk", new=AsyncMock(return_value="x.sip.vobiz.ai")), \
         patch("app.api.sip_trunks.LiveKitAPI", return_value=lk), \
         patch("app.workers.tasks.campaign.run_campaign.apply_async", dispatch):
        yield lk, dispatch


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


# ── Key and switches ──────────────────────────────────────────────────────────

async def test_not_configured_answers_503(client, db):
    resp = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    assert resp.status_code == 503
    assert await _count(db, Organization) == 0


async def test_wrong_or_missing_key_is_401(client, db, enabled):
    assert (await client.post(LAUNCH, json=_payload())).status_code == 401
    resp = await client.post(LAUNCH, json=_payload(), headers={"X-RevenueOS-Key": "x" * 40})
    assert resp.status_code == 401
    assert await _count(db, Organization) == 0


async def test_launch_switch_off_creates_nothing(client, db, enabled, monkeypatch):
    monkeypatch.setattr(settings, "REVENUEOS_LAUNCH_ENABLED", False)
    resp = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    assert resp.status_code == 503
    assert await _count(db, Organization) == 0


async def test_auto_start_switch_off_refuses_whole_request(client, db, enabled, monkeypatch):
    monkeypatch.setattr(settings, "REVENUEOS_AUTO_START_ENABLED", False)
    with _outside_world() as (_lk, dispatch):
        resp = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        assert resp.status_code == 503
        assert await _count(db, Organization) == 0

        # auto_start false is still allowed: stored, not started
        resp = await client.post(LAUNCH, json=_payload(auto_start=False), headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["start_status"] == "pending"
    dispatch.assert_not_called()


# ── Payload rules ─────────────────────────────────────────────────────────────

async def test_validation_error_names_the_field_and_never_echoes_secrets(client, db, enabled):
    body = _payload()
    del body["client_reference"]
    body["schedule"] = {"calling_days": ["someday"]}
    resp = await client.post(LAUNCH, json=body, headers=HEADERS)
    assert resp.status_code == 422
    fields = {e["field"] for e in resp.json()["errors"]}
    assert "client_reference" in fields
    assert "schedule.calling_days" in fields
    assert VOBIZ_TOKEN not in resp.text
    assert PASSWORD not in resp.text
    assert await _count(db, Organization) == 0


async def test_unknown_field_is_refused(client, db, enabled):
    resp = await client.post(LAUNCH, json=_payload(auto_strat=True), headers=HEADERS)
    assert resp.status_code == 422
    assert "auto_strat" in {e["field"] for e in resp.json()["errors"]}


async def test_no_usable_contact_creates_nothing(client, db, enabled):
    resp = await client.post(LAUNCH, json=_payload(contacts=[{"name": "X", "phone": "abc"}]), headers=HEADERS)
    assert resp.status_code == 422
    assert await _count(db, Organization) == 0


# ── Scenario 1: new account ───────────────────────────────────────────────────

async def test_new_account_creates_everything_and_starts(client, db, enabled):
    with _outside_world() as (lk, dispatch):
        resp = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["duplicate"] is False
    assert out["account"]["status"] == "created"
    assert out["phone_number"] == {"status": "connected", "number": "+912212345678"}
    assert out["agent"]["status"] == "created"
    assert out["start_status"] == "started"
    assert out["campaign"]["contacts_added"] == 2
    assert out["contacts_rejected"] == []
    assert VOBIZ_TOKEN not in resp.text and PASSWORD not in resp.text

    dispatch.assert_called_once()
    lk.sip.create_outbound_trunk.assert_awaited_once()
    lk.sip.create_sip_participant.assert_not_called()  # no test call, no call of any kind

    user = await db.scalar(select(User).where(User.email == "owner@acme-traders.example.com"))
    assert user.role == "admin" and user.email_verified_at is not None
    assert verify_password(PASSWORD, user.hashed_password)
    org = await db.get(Organization, user.org_id)
    assert org.is_active is True

    trunk = await db.scalar(select(SipTrunk).where(SipTrunk.org_id == org.id))
    assert trunk.is_active is True and trunk.is_default is True
    assert VOBIZ_TOKEN not in trunk.sip_password_encrypted  # stored encrypted

    campaign = await db.scalar(select(Campaign).where(Campaign.org_id == org.id))
    assert campaign.status == CampaignStatus.RUNNING
    assert campaign.is_prime is True
    assert campaign.sip_trunk_id == trunk.id
    phones = (await db.execute(
        select(CampaignContact.phone).where(CampaignContact.campaign_id == campaign.id)
    )).scalars().all()
    assert sorted(phones) == ["+919000000001", "+919000000002"]
    asha = await db.scalar(select(CampaignContact).where(CampaignContact.phone == "+919000000001"))
    assert asha.custom_fields["website"] == "ashafoods.example"

    profile = await db.scalar(select(OrgCompanyProfile).where(OrgCompanyProfile.org_id == org.id))
    assert profile.is_complete


# ── Idempotency ───────────────────────────────────────────────────────────────

async def test_same_payload_again_creates_nothing(client, db, enabled):
    with _outside_world() as (lk, dispatch):
        first = (await client.post(LAUNCH, json=_payload(), headers=HEADERS)).json()
        again = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    assert again.status_code == 200
    out = again.json()
    assert out["duplicate"] is True
    assert out["campaign"]["id"] == first["campaign"]["id"]
    assert out["start_status"] == "already_started"
    lk.sip.create_outbound_trunk.assert_awaited_once()
    for model in (Organization, User, SipTrunk, AgentTemplate, Campaign, RevenueOSClient, RevenueOSLaunch):
        assert await _count(db, model) == 1, model.__name__
    assert await _count(db, CampaignContact) == 2


async def test_same_reference_with_different_content_is_409(client, db, enabled):
    with _outside_world():
        await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        changed = _payload()
        changed["contacts"].append({"name": "New", "phone": "+919000000003"})
        resp = await client.post(LAUNCH, json=changed, headers=HEADERS)
    assert resp.status_code == 409
    assert await _count(db, Campaign) == 1
    assert await _count(db, CampaignContact) == 2


async def test_stored_but_not_started_then_started_by_repeat(client, db, enabled):
    with _outside_world() as (_lk, dispatch):
        first = await client.post(LAUNCH, json=_payload(auto_start=False), headers=HEADERS)
        assert first.json()["start_status"] == "pending"
        assert first.json()["campaign"]["status"] == "draft"
        dispatch.assert_not_called()

        again = await client.post(LAUNCH, json=_payload(auto_start=True), headers=HEADERS)
    assert again.json()["duplicate"] is True
    assert again.json()["start_status"] == "started"
    dispatch.assert_called_once()
    assert await _count(db, Campaign) == 1


# ── Scenarios 2–4: same account ───────────────────────────────────────────────

async def test_same_account_new_campaign_same_number(client, db, enabled):
    with _outside_world() as (lk, _dispatch):
        await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        second = _payload(reference="acme-campaign-2", campaign={"name": "November outreach"})
        second["contacts"] = [{"name": "Meera", "phone": "+919000000009"}]
        resp = await client.post(LAUNCH, json=second, headers=HEADERS)
    out = resp.json()
    assert resp.status_code == 200, resp.text
    assert out["account"]["status"] == "reused"
    assert out["phone_number"]["status"] == "reused"
    assert out["agent"]["status"] == "reused"  # same script → same agent
    lk.sip.create_outbound_trunk.assert_awaited_once()
    assert await _count(db, Organization) == 1
    assert await _count(db, SipTrunk) == 1
    assert await _count(db, Campaign) == 2


async def test_same_account_without_phone_block_reuses_its_number(client, db, enabled):
    with _outside_world():
        await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        second = _payload(reference="acme-campaign-2")
        del second["phone_number"]
        resp = await client.post(LAUNCH, json=second, headers=HEADERS)
    assert resp.json()["phone_number"] == {"status": "reused", "number": "+912212345678"}
    assert resp.json()["start_status"] in ("started", "blocked")  # blocked = org already at its call limit


async def test_same_account_different_number(client, db, enabled):
    with _outside_world() as (lk, _dispatch):
        await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        second = _payload(reference="acme-campaign-2")
        second["phone_number"]["did"] = "+912299999999"
        resp = await client.post(LAUNCH, json=second, headers=HEADERS)
    out = resp.json()
    assert out["account"]["status"] == "reused"
    assert out["phone_number"] == {"status": "connected", "number": "+912299999999"}
    assert lk.sip.create_outbound_trunk.await_count == 2
    assert await _count(db, SipTrunk) == 2
    campaign = await db.get(Campaign, UUID(out["campaign"]["id"]))
    trunk = await db.get(SipTrunk, campaign.sip_trunk_id)
    assert trunk.caller_id == "+912299999999"


async def test_existing_client_reference_with_other_email_is_409(client, db, enabled):
    with _outside_world():
        await client.post(LAUNCH, json=_payload(), headers=HEADERS)
        other = _payload(reference="acme-campaign-2")
        other["user"]["email"] = "someone-else@acme-traders.example.com"
        resp = await client.post(LAUNCH, json=other, headers=HEADERS)
    assert resp.status_code == 409
    assert await _count(db, User) == 1


# ── Partial success ───────────────────────────────────────────────────────────

async def test_bad_and_blocked_contacts_are_reported_and_the_rest_go_through(client, db, enabled):
    db.add(SystemDncEntry(phone_number="+919000000002", source="manual_admin"))
    await db.commit()
    body = _payload()
    body["contacts"] += [
        {"name": "Bad", "phone": "12"},
        {"name": "Twice", "phone": "+919000000001"},
    ]
    with _outside_world():
        resp = await client.post(LAUNCH, json=body, headers=HEADERS)
    out = resp.json()
    assert resp.status_code == 200, resp.text
    assert out["campaign"]["contacts_added"] == 1
    reasons = {r["phone"]: r["reason"] for r in out["contacts_rejected"]}
    assert reasons["12"] == "not a valid phone number"
    assert reasons["+919000000001"] == "listed more than once in this request"
    assert reasons["+919000000002"] == "on the do-not-call list"


async def test_number_that_fails_to_connect_keeps_the_account_and_can_be_retried(client, db, enabled):
    with _outside_world(vobiz_error=VobizAuthError("Invalid Vobiz auth_id or auth_token")) as (_lk, dispatch):
        resp = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    out = resp.json()
    assert resp.status_code == 200
    assert out["start_status"] == "blocked"
    assert out["account"]["status"] == "created"
    assert out["phone_number"]["status"] == "failed"
    assert out["campaign"] is None
    dispatch.assert_not_called()
    assert await _count(db, Organization) == 1
    assert await _count(db, Campaign) == 0

    with _outside_world():
        retry = await client.post(LAUNCH, json=_payload(), headers=HEADERS)
    assert retry.json()["account"]["status"] == "reused"
    assert retry.json()["start_status"] == "started"
    assert await _count(db, Organization) == 1


async def test_prime_without_company_profile_is_blocked(client, db, enabled):
    body = _payload()
    del body["company_profile"]
    with _outside_world() as (_lk, dispatch):
        resp = await client.post(LAUNCH, json=body, headers=HEADERS)
    out = resp.json()
    assert out["start_status"] == "blocked"
    assert "company_profile" in out["start_reason"]
    assert out["campaign"] is None
    dispatch.assert_not_called()


# ── Tenant isolation ──────────────────────────────────────────────────────────

def _second_client() -> dict:
    body = _payload(client_reference="client-zen", reference="zen-campaign-1")
    body["user"] = {
        "email": "owner@zen-labs.example.com", "password": "zen-password-123",
        "full_name": "Zen Owner", "company_name": "Zen Labs",
    }
    body["phone_number"] = {"auth_id": "MA_ZEN", "auth_token": "zen-vobiz-token", "did": "+913312345678"}
    body["contacts"] = [{"name": "Zed", "phone": "+918000000001"}]
    return body


async def test_second_client_cannot_see_or_touch_the_first(client, db, enabled):
    with _outside_world():
        acme = (await client.post(LAUNCH, json=_payload(), headers=HEADERS)).json()
        zen = (await client.post(LAUNCH, json=_second_client(), headers=HEADERS)).json()
    assert acme["account"]["organization_id"] != zen["account"]["organization_id"]

    acme_campaign = await db.get(Campaign, UUID(acme["campaign"]["id"]))
    db.add(Call(
        org_id=acme_campaign.org_id, campaign_id=acme_campaign.id, livekit_room_name="room-acme-1",
        phone_number="+919000000001", status=CallStatus.COMPLETED, outcome=CallOutcome.INTERESTED,
        summary="Acme private summary",
    ))
    await db.commit()

    base = "/api/integrations/revenueos/campaigns"
    # Acme's reference asked for under Zen's client_reference: not found, for every route
    for method, path in (
        ("get", f"{base}/acme-campaign-1"),
        ("get", f"{base}/acme-campaign-1/calls"),
        ("post", f"{base}/acme-campaign-1/pause"),
    ):
        resp = await getattr(client, method)(path, params={"client_reference": "client-zen"}, headers=HEADERS)
        assert resp.status_code == 404, path
        assert "Acme" not in resp.text
    await db.refresh(acme_campaign)
    assert acme_campaign.status == CampaignStatus.RUNNING  # the pause above did nothing

    # Zen's own calls list never contains Acme's call
    zen_calls = await client.get(
        f"{base}/zen-campaign-1/calls", params={"client_reference": "client-zen"}, headers=HEADERS
    )
    assert zen_calls.status_code == 200
    assert zen_calls.json()["items"] == []

    # Zen cannot reuse Acme's campaign reference, email or phone number
    with _outside_world():
        steal_ref = _second_client()
        steal_ref["reference"] = "acme-campaign-1"
        assert (await client.post(LAUNCH, json=steal_ref, headers=HEADERS)).status_code == 409

        steal_number = _second_client()
        steal_number["reference"] = "zen-campaign-2"
        steal_number["phone_number"]["did"] = "+912212345678"
        resp = await client.post(LAUNCH, json=steal_number, headers=HEADERS)
        assert resp.json()["start_status"] == "blocked"
        assert resp.json()["phone_number"]["status"] == "failed"

        new_client_old_email = _payload(client_reference="client-new", reference="new-1")
        assert (await client.post(LAUNCH, json=new_client_old_email, headers=HEADERS)).status_code == 409
    assert await _count(db, Organization) == 2


# ── Read side and pause ───────────────────────────────────────────────────────

async def test_status_calls_cursor_and_pause(client, db, enabled):
    with _outside_world():
        out = (await client.post(LAUNCH, json=_payload(), headers=HEADERS)).json()
    campaign = await db.get(Campaign, UUID(out["campaign"]["id"]))
    contact = await db.scalar(select(CampaignContact).where(CampaignContact.phone == "+919000000001"))

    call = Call(
        org_id=campaign.org_id, campaign_id=campaign.id, contact_id=contact.id,
        livekit_room_name="room-1", phone_number=contact.phone,
        status=CallStatus.COMPLETED, outcome=CallOutcome.INTERESTED,
        summary="Wants a quote", duration_seconds=95, ended_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.flush()
    db.add(CallTranscript(call_id=call.id, segments=[{"speaker": "agent", "text": "Namaste"}]))
    await db.commit()

    params = {"client_reference": "client-acme"}
    base = "/api/integrations/revenueos/campaigns/acme-campaign-1"

    status = (await client.get(base, params=params, headers=HEADERS)).json()
    assert status["status"] == "running"
    assert status["contacts_total"] == 2
    assert status["contacts_still_to_call"] == 2
    assert status["calls_by_outcome"] == {"interested": 1}

    calls = (await client.get(f"{base}/calls", params=params, headers=HEADERS)).json()
    assert len(calls["items"]) == 1
    item = calls["items"][0]
    assert item["outcome"] == "interested" and item["summary"] == "Wants a quote"
    assert item["contact"]["name"] == "Asha" and item["contact"]["company"] == "Asha Foods"
    assert item["transcript"] == [{"speaker": "agent", "text": "Namaste"}]
    assert item["finished"] is True
    assert calls["next_since"].endswith("Z")

    # Nothing changed since the cursor → empty page, cursor unchanged
    later = (await client.get(
        f"{base}/calls", params={**params, "since": calls["next_since"]}, headers=HEADERS
    )).json()
    assert later["items"] == []
    assert later["next_since"] == calls["next_since"]

    paused = (await client.post(f"{base}/pause", params=params, headers=HEADERS)).json()
    assert paused["paused"] is True and paused["status"] == "paused"
    await db.refresh(campaign)
    assert campaign.status == CampaignStatus.PAUSED

    assert (await client.get(base, params=params)).status_code == 401  # no key


# ── Billing switch ────────────────────────────────────────────────────────────

async def test_billing_switch_off_never_blocks_on_credits(db, monkeypatch):
    org = Organization(name="Spent Org", slug="spent-org", credits_used_this_period=10_000)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    assert await has_credits_remaining(db, org.id) is False
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)
    assert await has_credits_remaining(db, org.id) is True


async def test_billing_switch_off_new_signups_start_active(client, db, monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)
    with patch("app.api.auth.send_otp", new=AsyncMock()):
        resp = await client.post("/api/auth/register", json={
            "full_name": "Free User", "company_name": "Free Co",
            "email": "free-user@example.com", "password": "password-123", "phone": "9876543210",
        })
    assert resp.status_code == 201, resp.text
    org = await db.scalar(select(Organization).where(Organization.name == "Free Co"))
    assert org.is_active is True
