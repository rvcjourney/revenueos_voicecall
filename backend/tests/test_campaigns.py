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
