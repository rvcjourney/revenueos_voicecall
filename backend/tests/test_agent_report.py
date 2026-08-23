"""
tests/test_agent_report.py — POST /{call_id}/agent-report idempotency
(app/api/calls.py). The agent retries this POST with backoff
(agent/agent.py:_post_agent_report, up to 3 attempts) if its response is
ever lost after the backend already committed -- a redelivered report must
not double-count Campaign.interested_count or, for inbound calls,
double-bill credits / double-release the org's concurrency slot.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.security import hash_password, sign_webhook_payload
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.sip import SipTrunk, SipTransport
from app.models.user import Organization, User, UserRole


async def _post_report(client, call_id, payload: dict):
    body = json.dumps(payload).encode()
    return await client.post(
        f"/api/calls/{call_id}/agent-report",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)},
    )


# ── Outbound / campaign: interested_count must not double-count ────────────

async def _make_campaign_call(db) -> tuple[Organization, Campaign, Call]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    agent = AgentTemplate(org_id=org.id, name="Report Test Agent")
    db.add(agent)
    await db.flush()

    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Report Test Campaign")
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
        livekit_room_name=f"report-test-{uuid.uuid4().hex[:8]}",
        phone_number=contact.phone, direction=CallDirection.OUTBOUND,
        status=CallStatus.COMPLETED,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db.add(call)
    await db.commit()
    await db.refresh(campaign)
    await db.refresh(call)
    return org, campaign, call


async def test_agent_report_increments_interested_count_once(client, db):
    _org, campaign, call = await _make_campaign_call(db)

    resp = await _post_report(client, call.id, {"outcome": "interested", "summary": "Wants a callback."})
    assert resp.status_code == 204

    await db.refresh(campaign)
    assert campaign.interested_count == 1


async def test_agent_report_retry_does_not_double_count_interested(client, db):
    """Simulates the agent's own retry: the exact same report POSTed twice
    (e.g. the first response was lost to a network blip) must only count
    once toward the campaign's interested_count."""
    _org, campaign, call = await _make_campaign_call(db)
    payload = {"outcome": "interested", "summary": "Wants a callback."}

    first = await _post_report(client, call.id, payload)
    assert first.status_code == 204
    second = await _post_report(client, call.id, payload)  # retry
    assert second.status_code == 204

    await db.refresh(campaign)
    assert campaign.interested_count == 1  # not 2

    await db.refresh(call)
    assert call.reported_at is not None


async def test_agent_report_updates_outcome_on_retry_even_when_deduped(client, db):
    """The side effects (interested_count) are guarded, but re-applying the
    outcome/summary fields themselves on a retry is harmless and still
    expected to happen (e.g. a retry carrying a fuller transcript)."""
    _org, _campaign, call = await _make_campaign_call(db)

    first = await _post_report(client, call.id, {"outcome": "interested", "summary": "First summary."})
    assert first.status_code == 204
    second = await _post_report(client, call.id, {"outcome": "interested", "summary": "Updated summary."})
    assert second.status_code == 204

    await db.refresh(call)
    assert call.summary == "Updated summary."


# ── Inbound: double-billing / double-slot-release on retry ─────────────────

async def _make_inbound_setup(db):
    from app.core.concurrency import acquire_org_slot

    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"), full_name="Admin",
        role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)

    trunk = SipTrunk(
        org_id=org.id, name="Vobiz +912212345678", livekit_trunk_id="ST_outbound_abc",
        sip_domain="abc123.sip.vobiz.ai", sip_username="real_id", sip_password="super-secret",
        caller_id="+912212345678", transport=SipTransport.TCP, is_default=True, is_active=True,
    )
    db.add(trunk)
    await db.commit()
    await db.refresh(org)
    await db.refresh(trunk)

    call = Call(
        org_id=org.id, sip_trunk_id=trunk.id,
        livekit_room_name=f"inbound-report-test-{uuid.uuid4().hex[:8]}",
        phone_number="+919876543210", direction=CallDirection.INBOUND,
        status=CallStatus.CONNECTED,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=90),
        answered_at=datetime.now(timezone.utc) - timedelta(seconds=90),
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Mirror start_inbound_call's accept-time slot acquisition.
    await acquire_org_slot(org.id, 1)
    return org, call


async def test_agent_report_retry_does_not_double_bill_inbound_credits(client, db, fake_redis):
    import app.workers.tasks.campaign as campaign_module

    org, call = await _make_inbound_setup(db)
    payload = {"outcome": "interested", "summary": "Asked about pricing.", "transcript": []}

    with patch.object(campaign_module.fetch_recording_for_inbound_call, "apply_async", MagicMock()):
        first = await _post_report(client, call.id, payload)
        assert first.status_code == 204
        second = await _post_report(client, call.id, payload)  # retry
        assert second.status_code == 204

    await db.refresh(org)
    assert org.credits_used_this_period == 2  # ceil(90s / 60) billed exactly once


async def test_agent_report_retry_does_not_double_release_org_slot(client, db, fake_redis):
    import app.workers.tasks.campaign as campaign_module
    from app.core.concurrency import acquire_org_slot, get_current_usage

    org, call = await _make_inbound_setup(db)
    payload = {"outcome": "interested", "summary": "Asked about pricing.", "transcript": []}

    with patch.object(campaign_module.fetch_recording_for_inbound_call, "apply_async", MagicMock()):
        await _post_report(client, call.id, payload)
        await _post_report(client, call.id, payload)  # retry

    usage = await get_current_usage(db, org.id)
    assert usage["in_use"] == 0  # released exactly once, not floored-at-zero after over-releasing

    # A second, genuinely new call should be able to acquire the org's one
    # slot cleanly -- would still pass even with a double-release bug (floor
    # at 0), so this alone isn't sufficient, but combined with the in_use
    # assertion above it confirms no negative-count corruption happened.
    assert await acquire_org_slot(org.id, 1) is True
