"""
tests/test_prime_calling.py — Prime Calling (per-contact personalised prompts).

Covers:
  - website_reader refuses non-public / non-http targets (SSRF guard) and
    extracts readable text from HTML.
  - prime_prompt parses LLM JSON, falls back cleanly, and the dispatcher helper
    never raises / saves the generated prompt for reuse on retries.
  - CSV upload recognises a "Contact" phone column and keeps extra columns.
  - Company profile API + launch gate for Prime campaigns.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.agent import AgentTemplate
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.user import Organization, User, UserRole
from app.services import prime_prompt, website_reader
from app.services.prime_prompt import ContactInfo


# ── website_reader ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://localhost:8000/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://[::1]/",
])
async def test_website_reader_blocks_private_addresses(url, fake_redis):
    with patch.object(website_reader.httpx.AsyncClient, "stream") as stream:
        assert await website_reader.fetch_site_summary(url) == ""
        stream.assert_not_called()


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com", "javascript:alert(1)", ""])
def test_website_reader_rejects_non_http(url):
    assert website_reader.normalize_url(url) is None


def test_normalize_url_adds_scheme():
    assert website_reader.normalize_url("acme.com") == "https://acme.com"


def test_html_to_summary_extracts_text():
    html = """<html><head><title> Acme  Steel </title>
    <meta name="description" content="Industrial steel supplier"></head>
    <body><script>var x=1;</script><h1>We make pipes</h1><p>Since 1990</p></body></html>"""
    summary = website_reader.html_to_summary(html)
    assert "Title: Acme Steel" in summary
    assert "Industrial steel supplier" in summary
    assert "We make pipes Since 1990" in summary
    assert "var x" not in summary


# ── prime_prompt ──────────────────────────────────────────────────────────────

def _contact(**custom):
    return ContactInfo(name="Ravi", phone="+919876543210", email=None, company="Acme", custom_fields=custom)


def test_find_website_from_custom_fields():
    assert prime_prompt.find_website(_contact(designation="CEO", website="acme.com")) == "acme.com"
    assert prime_prompt.find_website(_contact(designation="CEO")) is None


def _llm_json(prompt: str, welcome: str = "Namaste ji! Main Priya bol rahi hoon MOTM se.") -> str:
    import json
    return json.dumps({"system_prompt": prompt, "welcome_message": welcome})


_SECTIONS_0_TO_6 = "# SYSTEM PROMPT\n" + "\n".join(f"## {i}. SECTION\nbody" for i in range(7))


def test_parse_output_appends_fixed_section_7():
    prompt, welcome, leftovers = prime_prompt._parse_output("```json\n" + _llm_json(_SECTIONS_0_TO_6) + "\n```")
    assert welcome.startswith("Namaste ji") and leftovers == []
    assert prompt.startswith("# SYSTEM PROMPT")
    assert prompt.endswith(prime_prompt.SECTION_7)
    assert "[end_call]" in prompt


def test_parse_output_replaces_llm_written_section_7():
    raw = _SECTIONS_0_TO_6 + "\n## 7. CALL ENDING\nsay nothing after namaste"
    prompt, _, _ = prime_prompt._parse_output(_llm_json(raw))
    assert "say nothing after namaste" not in prompt
    assert prompt.count("## 7.") == 1


def test_parse_output_rejects_missing_sections_or_bad_welcome():
    with pytest.raises(ValueError, match="missing sections"):
        prime_prompt._parse_output(_llm_json("# SYSTEM PROMPT\n## 0. WHO\n## 1. RULES"))
    with pytest.raises(ValueError, match="placeholders"):
        prime_prompt._parse_output(_llm_json(_SECTIONS_0_TO_6, welcome="Namaste [prospect name] ji"))
    with pytest.raises(ValueError):
        prime_prompt._parse_output('{"system_prompt": "", "welcome_message": ""}')


def test_parse_output_reports_leftover_placeholders():
    raw = _SECTIONS_0_TO_6 + "\nconnect to [the decision-maker if known]. Callback at [time/date]."
    _, _, leftovers = prime_prompt._parse_output(_llm_json(raw))
    assert leftovers == ["[the decision-maker if known]"]  # [time/date] is allowed


def _profile():
    from types import SimpleNamespace
    return SimpleNamespace(
        company_name="MOTM", website=None, industry=None, what_we_offer="Leads", value_proposition=None,
        target_customers=None, key_points=None, call_objective=None, tone_notes=None, extra_info=None,
    )


async def test_generate_asks_model_to_fix_leftover_placeholders():
    from app.config import settings

    with_leftover = _llm_json(_SECTIONS_0_TO_6 + "\nask for [the decision-maker]")
    fixed = _llm_json(_SECTIONS_0_TO_6 + "\nask for Ravi ji")
    groq = AsyncMock(side_effect=[with_leftover, fixed])
    with patch.object(settings, "GROQ_API_KEY", "test-key"), patch.object(prime_prompt, "_call_groq", groq):
        result = await prime_prompt.generate_contact_prompt(
            profile=_profile(), base_prompt="BASE", language="hinglish", contact=_contact(),
        )
    assert "Ravi ji" in result.system_prompt and "[the decision-maker]" not in result.system_prompt
    fix_messages = groq.await_args_list[1].args[1]
    assert [m["role"] for m in fix_messages] == ["user", "assistant", "user"]
    assert "[the decision-maker]" in fix_messages[-1]["content"]


async def test_generate_accepts_prompt_if_placeholders_never_fixed():
    from app.config import settings

    with_leftover = _llm_json(_SECTIONS_0_TO_6 + "\nask for [the decision-maker]")
    groq = AsyncMock(return_value=with_leftover)
    with patch.object(settings, "GROQ_API_KEY", "test-key"), patch.object(prime_prompt, "_call_groq", groq):
        result = await prime_prompt.generate_contact_prompt(
            profile=_profile(), base_prompt="BASE", language="hinglish", contact=_contact(),
        )
    assert groq.await_count == 3
    assert result.system_prompt.startswith("# SYSTEM PROMPT")


def test_template_fills_gatekeeper_target_in_code():
    text = prime_prompt._META_PROMPT.format(
        company="MOTM", prospect_ref="Ravi ji (by name)", prospect_ask="Ravi ji",
        language="hinglish", profile="", base_prompt="", contact="",
    )
    assert "connected to Ravi ji (by name)." in text
    assert "Kya Ravi ji se baat ho sakti hai" in text


def test_fallback_prompt_appends_contact_details():
    prompt, welcome = prime_prompt.fallback_prompt("BASE", "Hello", _contact(designation="CFO"))
    assert prompt.startswith("BASE")
    assert "designation: CFO" in prompt and "company: Acme" in prompt
    assert welcome == "Hello"


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _setup(db, *, is_prime=True, with_profile=True):
    from app.models.company_profile import OrgCompanyProfile

    org = Organization(name="Prime Org", slug="prime-org")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email="admin@prime.test", hashed_password=hash_password("pw-123456"),
        full_name="Prime Admin", role=UserRole.ADMIN, is_active=True,
    )
    agent = AgentTemplate(org_id=org.id, name="Agent", system_prompt="BASE PROMPT", welcome_message="Hi")
    db.add_all([user, agent])
    await db.flush()
    campaign = Campaign(
        org_id=org.id, agent_template_id=agent.id, name="Prime", status=CampaignStatus.DRAFT,
        is_prime=is_prime, created_by_id=user.id,
    )
    db.add(campaign)
    if with_profile:
        db.add(OrgCompanyProfile(org_id=org.id, company_name="MOTM", what_we_offer="Voice AI"))
    await db.commit()
    await db.refresh(user)
    await db.refresh(campaign)
    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, campaign, {"Authorization": f"Bearer {token}"}


# ── CSV upload ────────────────────────────────────────────────────────────────

async def test_upload_recognises_contact_column_and_keeps_extras(client, db):
    _, campaign, headers = await _setup(db)
    csv_bytes = (
        "Name,Designation,Contact,Company Name,Website,Location\n"
        "Ravi Kumar,CEO,9876543210,Acme Steel,acme.com,Pune\n"
    ).encode()
    resp = await client.post(
        f"/api/campaigns/{campaign.id}/contacts", headers=headers,
        files={"file": ("contacts.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 201, resp.text

    contact = (await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == campaign.id)
    )).scalar_one()
    assert contact.name == "Ravi Kumar"
    assert contact.phone == "+919876543210"
    assert contact.company == "Acme Steel"
    assert contact.custom_fields == {"designation": "CEO", "website": "acme.com", "location": "Pune"}


# ── Company profile + launch gate ─────────────────────────────────────────────

async def test_company_profile_roundtrip(client, db):
    _, _, headers = await _setup(db, with_profile=False)
    resp = await client.get("/api/company-profile", headers=headers)
    assert resp.status_code == 200 and resp.json()["is_complete"] is False

    resp = await client.put("/api/company-profile", headers=headers,
                            json={"company_name": "MOTM", "what_we_offer": "AI calling"})
    assert resp.status_code == 200 and resp.json()["is_complete"] is True


async def test_launch_prime_campaign_requires_profile(client, db):
    _, campaign, headers = await _setup(db, with_profile=False)
    resp = await client.post(f"/api/campaigns/{campaign.id}/launch", headers=headers)
    # Draft has no contacts, but the profile check must fire first
    assert resp.status_code == 422
    assert "Company Profile" in resp.text


async def test_campaign_list_filters_by_is_prime(client, db):
    _, campaign, headers = await _setup(db)
    prime = (await client.get("/api/campaigns?is_prime=true", headers=headers)).json()
    normal = (await client.get("/api/campaigns?is_prime=false", headers=headers)).json()
    assert [c["id"] for c in prime["items"]] == [str(campaign.id)]
    assert normal["items"] == []


# ── dispatcher helper ─────────────────────────────────────────────────────────

async def test_prepare_prime_prompt_saves_and_reuses(db_engine, db):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.workers.tasks import campaign as campaign_task

    org, campaign, _ = await _setup(db)
    contact = CampaignContact(org_id=org.id, campaign_id=campaign.id, name="Ravi", phone="+911",
                              custom_fields={"designation": "CEO"})
    db.add(contact)
    await db.commit()

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    generated = prime_prompt.GeneratedPrompt("PERSONAL PROMPT", "Namaste Ravi ji", website_used=False)
    kwargs = dict(contact_id=contact.id, org_id=org.id, base_prompt="BASE", base_welcome="Hi", language="hinglish")

    with patch.object(campaign_task, "AsyncSessionLocal", factory), \
            patch("app.services.prime_prompt.generate_contact_prompt", new=AsyncMock(return_value=generated)) as gen:
        assert await campaign_task._prepare_prime_prompt(**kwargs) == ("PERSONAL PROMPT", "Namaste Ravi ji")
        # Second attempt (retry) reuses the saved prompt without calling the LLM again
        assert await campaign_task._prepare_prime_prompt(**kwargs) == ("PERSONAL PROMPT", "Namaste Ravi ji")
        assert gen.await_count == 1


async def test_prepare_prime_prompt_falls_back_on_llm_failure(db_engine, db):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.workers.tasks import campaign as campaign_task

    org, campaign, _ = await _setup(db)
    contact = CampaignContact(org_id=org.id, campaign_id=campaign.id, name="Ravi", phone="+911",
                              company="Acme", custom_fields={})
    db.add(contact)
    await db.commit()

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(campaign_task, "AsyncSessionLocal", factory), \
            patch("app.services.prime_prompt.generate_contact_prompt",
                  new=AsyncMock(side_effect=RuntimeError("groq down"))):
        prompt, welcome = await campaign_task._prepare_prime_prompt(
            contact_id=contact.id, org_id=org.id, base_prompt="BASE", base_welcome="Hi", language="hinglish",
        )
    assert prompt.startswith("BASE") and "company: Acme" in prompt and welcome == "Hi"

    async with factory() as s:
        saved = await s.get(CampaignContact, contact.id)
    assert saved.prompt_error == "groq down" and saved.generated_system_prompt is None
