"""
tests/test_campaigns.py — Campaign API tests.

Covers duplicate_campaign's copy_contacts option (backend/app/api/campaigns.py):
default behavior (copy_contacts=true, the pre-existing behavior) must be
unchanged, and copy_contacts=false must skip the contact copy entirely --
this is what the "duplicate with fresh data" frontend flow relies on to avoid
mixing a freshly-uploaded contact list with contacts copied from the original
campaign (CampaignDetail.tsx's DuplicateCampaignDialog).
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.agent import AgentTemplate
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.user import Organization, User, UserRole


async def _make_campaign_with_contacts(db, *, contact_count: int = 2):
    org = Organization(name="Dup Test Org", slug="dup-test-org")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email="admin@duptest.test",
        hashed_password=hash_password("user-pw-123"),
        full_name="Dup Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)

    agent = AgentTemplate(org_id=org.id, name="Test Agent")
    db.add(agent)
    await db.flush()

    campaign = Campaign(
        org_id=org.id,
        agent_template_id=agent.id,
        name="Original Campaign",
        status=CampaignStatus.DRAFT,
    )
    db.add(campaign)
    await db.flush()

    for i in range(contact_count):
        db.add(CampaignContact(
            org_id=org.id,
            campaign_id=campaign.id,
            name=f"Contact {i}",
            phone=f"+9112345678{i}",
        ))
    campaign.total_contacts = contact_count

    await db.commit()
    await db.refresh(campaign)
    await db.refresh(user)
    return org, user, campaign


async def test_duplicate_campaign_copies_contacts_by_default(client, db):
    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=3)
    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.post(
        f"/api/campaigns/{campaign.id}/duplicate", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]
    assert resp.json()["total_contacts"] == 3

    copied = (await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == new_id)
    )).scalars().all()
    assert len(copied) == 3


async def test_duplicate_campaign_skips_contacts_when_requested(client, db):
    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=3)
    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.post(
        f"/api/campaigns/{campaign.id}/duplicate?copy_contacts=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]
    assert resp.json()["total_contacts"] == 0

    copied = (await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == new_id)
    )).scalars().all()
    assert len(copied) == 0

    # Original campaign's own contacts must be untouched.
    original_contacts = (await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == campaign.id)
    )).scalars().all()
    assert len(original_contacts) == 3


async def test_campaign_with_only_no_answer_contacts_completes(db_engine, db):
    """Regression: NO_ANSWER is terminal, so a campaign left with only those
    contacts must COMPLETE — it used to wait for a retry that never came, and
    the dispatcher looped forever (watchdog re-queued it every ~6 minutes)."""
    import asyncio
    from datetime import time as dt_time
    from unittest.mock import AsyncMock, patch

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.campaign import ContactStatus
    from app.workers.tasks import campaign as campaign_task

    org, _, campaign = await _make_campaign_with_contacts(db, contact_count=2)
    campaign.status = CampaignStatus.RUNNING
    campaign.calling_window_start = dt_time(0, 0)
    campaign.calling_window_end = dt_time(23, 59)
    campaign.calling_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    for contact in (await db.execute(select(CampaignContact))).scalars():
        contact.status = ContactStatus.NO_ANSWER
    await db.commit()

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(campaign_task, "AsyncSessionLocal", factory), \
            patch.object(campaign_task, "has_credits_remaining", new=AsyncMock(return_value=True)):
        await asyncio.wait_for(campaign_task._dispatch_loop(None, str(campaign.id)), timeout=10)

    async with factory() as s:
        assert (await s.get(Campaign, campaign.id)).status == CampaignStatus.COMPLETED


async def test_dispatcher_tells_agent_when_brochure_can_be_sent(db_engine, db):
    """The agent only offers the brochure when the agent has one AND the org has a
    mailbox; and it knows per contact whether an email is already on file."""
    import asyncio
    from datetime import time as dt_time
    from unittest.mock import AsyncMock, patch

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.crypto import encrypt_value
    from app.models.campaign import ContactStatus
    from app.workers.tasks import campaign as campaign_task

    org, _, campaign = await _make_campaign_with_contacts(db, contact_count=2)
    campaign.status = CampaignStatus.RUNNING
    campaign.calling_window_start, campaign.calling_window_end = dt_time(0, 0), dt_time(23, 59)
    campaign.calling_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    agent = await db.get(AgentTemplate, campaign.agent_template_id)
    agent.brochure_key, agent.brochure_filename = "brochures/x.pdf", "x.pdf"
    agent.gcal_refresh_token = encrypt_value("refresh")
    org.smtp_host, org.smtp_port, org.smtp_security = "smtp.acme.in", 587, "starttls"
    org.smtp_from_email = org.smtp_username = "sales@acme.in"
    org.smtp_password = encrypt_value("pw")
    contacts = (await db.execute(select(CampaignContact).order_by(CampaignContact.phone))).scalars().all()
    contacts[0].email = "c0@x.in"
    await db.commit()

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    placed = []

    async def fake_call(*_args, **kw):
        placed.append(kw)
        async with factory() as s:  # finish the contact so the dispatcher can complete
            await s.execute(
                CampaignContact.__table__.update().where(CampaignContact.id == kw["contact_id"])
                .values(status=ContactStatus.COMPLETED)
            )
            await s.commit()

    with patch.object(campaign_task, "AsyncSessionLocal", factory), \
            patch.object(campaign_task, "has_credits_remaining", new=AsyncMock(return_value=True)), \
            patch.object(campaign_task, "_resolve_trunk", new=AsyncMock(return_value=("trunk", "+911234567890"))), \
            patch.object(campaign_task.pipelines, "call_meta", new=AsyncMock(return_value={"sarvam": {"language": "hindi"}})), \
            patch.object(campaign_task, "_run_one_call", new=fake_call):
        await asyncio.wait_for(campaign_task._dispatch_loop(None, str(campaign.id)), timeout=15)

    by_phone = {kw["contact_phone"]: kw["extra_meta"] for kw in placed}
    assert by_phone["+91123456780"] == {
        "sarvam": {"language": "hindi"},
        "brochure": {"available": True, "email_on_file": True},
        "calendar": {"available": True, "email_on_file": True, "agent_id": str(agent.id)},
        "transfer": {"number": ""},
    }
    assert by_phone["+91123456781"]["brochure"] == {"available": True, "email_on_file": False}
    assert by_phone["+91123456781"]["calendar"]["email_on_file"] is False


async def test_campaign_language_is_saved_validated_and_copied(client, db):
    """A campaign can run its agent in another language (Tamil campaign, Hindi agent)."""
    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=1)
    token = create_access_token(str(user.id), str(user.org_id), user.role)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"name": "Tamil Nadu outreach", "agent_template_id": str(campaign.agent_template_id)}

    created = await client.post("/api/campaigns", json={**body, "language": "tamil"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["language"] == "tamil"

    # Blank/omitted = inherit the agent template's own language
    inherited = await client.post("/api/campaigns", json={**body, "language": ""}, headers=headers)
    assert inherited.status_code == 201 and inherited.json()["language"] is None
    assert (await client.post("/api/campaigns", json=body, headers=headers)).json()["language"] is None

    # Unsupported languages are rejected, not silently stored
    rejected = await client.post("/api/campaigns", json={**body, "language": "french"}, headers=headers)
    assert rejected.status_code in (400, 422)

    # Duplicating a campaign keeps its language
    dup = await client.post(f"/api/campaigns/{created.json()['id']}/duplicate", headers=headers)
    assert dup.status_code == 201 and dup.json()["language"] == "tamil"


async def test_campaign_voice_override_is_saved_validated_and_copied(client, db):
    """A campaign can speak with one of the org's own cloned voices directly,
    instead of being stuck with whatever voice its agent template has."""
    from app.models.cloned_voice import ClonedVoice

    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=1)
    other_org = Organization(name="Other Org", slug="other-org-voice-test")
    db.add(other_org)
    await db.flush()

    my_voice = ClonedVoice(org_id=org.id, name="My Voice", elevenlabs_voice_id="voice-mine-123", provider="sarvam")
    other_voice = ClonedVoice(org_id=other_org.id, name="Their Voice", elevenlabs_voice_id="voice-theirs-456", provider="sarvam")
    db.add_all([my_voice, other_voice])
    await db.commit()

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"name": "Direct voice outreach", "agent_template_id": str(campaign.agent_template_id)}

    created = await client.post(
        "/api/campaigns", json={**body, "voice_id": "voice-mine-123"}, headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["voice_id"] == "voice-mine-123"

    # Blank/omitted = inherit the agent template's own voice
    inherited = await client.post("/api/campaigns", json={**body, "voice_id": ""}, headers=headers)
    assert inherited.status_code == 201 and inherited.json()["voice_id"] is None
    assert (await client.post("/api/campaigns", json=body, headers=headers)).json()["voice_id"] is None

    # Someone else's cloned voice is rejected, not silently stored
    other_orgs = await client.post(
        "/api/campaigns", json={**body, "voice_id": "voice-theirs-456"}, headers=headers
    )
    assert other_orgs.status_code in (400, 403, 422)

    # A made-up voice id is rejected too (it's not any ClonedVoice row at all)
    made_up = await client.post(
        "/api/campaigns", json={**body, "voice_id": "not-a-real-voice"}, headers=headers
    )
    assert made_up.status_code in (400, 403, 422)

    # Duplicating a campaign keeps its voice override
    dup = await client.post(f"/api/campaigns/{created.json()['id']}/duplicate", headers=headers)
    assert dup.status_code == 201 and dup.json()["voice_id"] == "voice-mine-123"


async def test_campaign_requires_an_agent(client, db):
    """The agent's Greeting + Instructions are the call script."""
    org, user, _ = await _make_campaign_with_contacts(db, contact_count=0)
    token = create_access_token(str(user.id), str(user.org_id), user.role)
    headers = {"Authorization": f"Bearer {token}"}

    rejected = await client.post(
        "/api/campaigns",
        json={"name": "Without an agent"},
        headers=headers,
    )
    assert rejected.status_code in (400, 422)


async def test_calling_hours_saved_on_create_and_edit_and_validated(client, db):
    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=1)
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id), str(user.org_id), user.role)}"}
    body = {"name": "Night shift", "agent_template_id": str(campaign.agent_template_id)}

    # Defaults unchanged when not sent
    default = (await client.post("/api/campaigns", json=body, headers=headers)).json()
    assert default["calling_window_start"] == "09:00:00" and default["calling_window_end"] == "19:00:00"
    assert default["calling_days"] == ["mon", "tue", "wed", "thu", "fri", "sat"]

    created = await client.post("/api/campaigns", json={
        **body, "calling_window_start": "10:30", "calling_window_end": "22:00", "calling_days": ["sun", "mon"],
    }, headers=headers)
    assert created.status_code == 201, created.text
    c = created.json()
    assert (c["calling_window_start"], c["calling_window_end"], c["calling_days"]) == ("10:30:00", "22:00:00", ["mon", "sun"])

    for bad in ({"calling_window_start": "20:00", "calling_window_end": "09:00"},
                {"calling_days": []}, {"calling_days": ["funday"]}):
        assert (await client.post("/api/campaigns", json={**body, **bad}, headers=headers)).status_code == 422

    edited = await client.patch(f"/api/campaigns/{c['id']}", json={"calling_window_end": "23:00", "calling_days": ["sat"]},
                                headers=headers)
    assert edited.status_code == 200 and edited.json()["calling_window_end"] == "23:00:00"
    assert edited.json()["calling_days"] == ["sat"]
    # End before the saved start is refused
    assert (await client.patch(f"/api/campaigns/{c['id']}", json={"calling_window_end": "08:00"},
                               headers=headers)).status_code in (400, 422)
