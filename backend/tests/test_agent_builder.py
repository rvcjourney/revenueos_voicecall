"""
tests/test_agent_builder.py — "Customise with AI" (POST /api/agents/customize)
and the campaign preview (GET /api/campaigns/{id}/preview). Sarvam is faked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.core.security import create_access_token
from app.models.agent import AgentTemplate
from app.models.campaign import CampaignContact
from tests.test_campaigns import _make_campaign_with_contacts


async def _headers(db):
    org, user, campaign = await _make_campaign_with_contacts(db, contact_count=0)
    return org, campaign, {"Authorization": f"Bearer {create_access_token(str(user.id), str(user.org_id), user.role)}"}


async def test_customize_returns_the_rewritten_script_without_saving(client, db):
    _, _, h = await _headers(db)
    fake = AsyncMock(return_value=("Made it formal.", "Good morning {userName}.", "## Persona\n- Formal."))
    with patch("app.services.agent_builder.customize", new=fake):
        r = await client.post("/api/agents/customize", headers=h, json={
            "greeting": "Hi {userName}", "instructions": "## Persona\n- Casual.", "request": "make it formal"})
    assert r.status_code == 200, r.text
    assert r.json() == {"summary": "Made it formal.", "greeting": "Good morning {userName}.",
                        "instructions": "## Persona\n- Formal."}
    assert fake.await_args.kwargs["request"] == "make it formal"


async def test_customize_turns_ai_failures_into_a_readable_error(client, db):
    from app.services.agent_builder import AgentBuilderError
    _, _, h = await _headers(db)
    with patch("app.services.agent_builder.customize", new=AsyncMock(side_effect=AgentBuilderError("Try again."))):
        r = await client.post("/api/agents/customize", headers=h, json={"request": "write a script"})
    assert r.status_code == 422 and "Try again." in r.text
    assert (await client.post("/api/agents/customize", headers=h, json={"request": " "})).status_code == 422


async def test_preview_fills_placeholders_per_contact_and_lists_gaps(client, db):
    org, campaign, h = await _headers(db)
    agent = await db.get(AgentTemplate, campaign.agent_template_id)
    agent.welcome_message = "Hi {userName}, Ananya from {partnerName}."
    agent.system_prompt = "Talk about {productCategory}. Today is {current_date}."
    agent.variables = {"partnerName": "Acme"}
    db.add_all([
        CampaignContact(org_id=org.id, campaign_id=campaign.id, name="A", phone="+911111111111",
                        custom_fields={"user_name": "Ravi", "productcategory": "steel"}),
        CampaignContact(org_id=org.id, campaign_id=campaign.id, name="B", phone="+912222222222",
                        custom_fields={"user_name": "Sita"}),
    ])
    await db.commit()

    body = (await client.get(f"/api/campaigns/{campaign.id}/preview", headers=h)).json()
    assert body["total_contacts"] == 2
    assert body["variables"] == ["userName", "partnerName", "productCategory", "current_date"]
    assert body["missing"] == ["productCategory"]
    first, second = body["items"]
    assert first["welcome_message"] == "Hi Ravi, Ananya from Acme."
    assert first["system_prompt"].startswith("Talk about steel. Today is ") and first["missing"] == []
    assert second["missing"] == ["productCategory"]
