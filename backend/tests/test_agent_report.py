"""
tests/test_agent_report.py — POST /{call_id}/agent-report idempotency
(app/api/calls.py). The agent retries this POST with backoff
(agent/agent.py:_post_agent_report, up to 3 attempts) if its response is
ever lost after the backend already committed -- a redelivered report must
not double-count Campaign.interested_count.
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
