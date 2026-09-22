"""
tests/test_prime_calling.py — Prime Calling (per-contact personalised prompts).

Covers:
  - website_reader refuses non-public / non-http targets (SSRF guard) and
    extracts readable text from HTML.
  - prime_prompt builds the script from kit + brief, falls back OpenAI → Groq, and the dispatcher helper
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


def test_pick_key_pages_prefers_same_site_about_and_products():
    links = [
        "/about-us", "https://acme.com/products/", "https://other.com/about", "/blog/2024/05/post/x",
        "/products/gear-a", "mailto:x@acme.com", "/brochure.pdf", "/contact", "#top",
    ]
    pages = website_reader.pick_key_pages(links, "https://www.acme.com/")
    assert pages[0] == "https://www.acme.com/about-us"
    assert "https://acme.com/products/" in pages
    assert len(pages) == 2  # one page per keyword; other sites, files and blog posts skipped


def _kit(**overrides):
    kit = {
        "agent_name": "Priya", "agent_gender": "female", "company_city": "Pune",
        "company_one_liner": "a Pune-based lead-generation agency for manufacturers",
        "company_overview_spoken": "Hum manufacturers ke liye leads generate karte hain.",
        "cta": "free business diagnosis call", "cta_is_free": True,
        "business_kind_we_serve": "a manufacturing business",
        "company_overview": ["Name: MOTM", "Focus: B2B lead generation"],
        "core_solutions": [{"name": "Lead Generation", "description": "Qualified B2B leads"}],
        "proof_points": ["Helped a Rajkot valve maker get 40 enquiries in 3 months (valves)"],
        "how_we_work": [], "industries_served": ["Engineering"], "contact_info": [],
        "website_spoken": "www dot motm dot in",
        "sample_answers": [{"question": "Aap log kya karte ho?", "answer": "Hum leads laate hain."}],
        "company_name": "MOTM",
    }
    kit.update(overrides)
    return kit


def _brief(**overrides):
    brief = {
        "prospect_facts": ["Name: Ravi", "Company: Acme Gears, makes CNC gears for auto OEMs"],
        "industry_label": "gear manufacturing",
        "relevance_points": ["Gear makers rely on a few big buyers"],
        "likely_pains": ["Dependence on 2–3 OEM buyers"],
        "timely_hook": "Maine dekha aapne Chakan mein naya unit shuru kiya hai.",
        "welcome_message": "Namaste ji! Main Priya bol rahi hoon MOTM se, Pune. Kya main Ravi ji se baat kar sakti hoon?",
        "opening_value_line": "Hum gear manufacturing companies ke liye naye buyers laate hain.",
        "qualify_question_1": "Main dekh rahi thi aap auto OEMs ke liye gears banate hain — sahi hai?",
        "branch_b_question": "Aap mainly OEMs ko supply karte hain ya aftermarket ko bhi?",
        "gatekeeper_purpose": "Acme ke naye buyers ke silsile mein ek chhoti si baat thi.",
        "why_we_called_answer": "Aap gear manufacturing mein hain, aur hum aise hi businesses ki madad karte hain.",
        "best_fit_solutions": [{"solution": "Lead Generation", "why": "New OEM buyers"}],
        "relevant_proof": ["Helped a Rajkot valve maker get 40 enquiries in 3 months"],
        "objections": [{"objection": "Budget nahi hai", "response": "Samjhi ji, call free hai. Kya dekh lein?"}],
    }
    brief.update(overrides)
    return brief


def _build(kit=None, brief=None, name="Ravi", has_name=True):
    return prime_prompt.build_prompt(
        kit=kit or _kit(), brief=brief or _brief(), contact_name=name, has_name=has_name,
        language="hinglish", default_welcome="Namaste ji! Main Priya bol rahi hoon MOTM se.",
    )


def test_build_prompt_fills_every_section_in_code():
    import re

    prompt, welcome = _build()
    for i in range(8):
        assert f"\n## {i}." in prompt
    assert prompt.endswith(prime_prompt.SECTION_7)
    assert welcome.startswith("Namaste ji! Main Priya")
    assert "Chakan" in prompt and "Budget nahi hai" in prompt and "Rajkot valve" in prompt
    assert "common challenge hai gear manufacturing businesses" in prompt
    assert "connected to Ravi ji (by name)." in prompt and "Kya Ravi ji se baat ho sakti hai" in prompt
    assert "free business diagnosis call bilkul free hai" in prompt
    assert "www dot motm dot in" in prompt
    # No template markers or placeholders left — only the two allowed bracket tokens
    assert "{{" not in prompt and "[[" not in prompt
    assert set(re.findall(r"\[[^\]\n]*\]", prompt)) <= {"[time/date]", "[end_call]"}


def test_build_prompt_uses_male_forms_and_unknown_name():
    prompt, _ = _build(kit=_kit(agent_name="Rahul", agent_gender="male"), name="", has_name=False)
    assert "Rahul bol raha hoon" in prompt
    assert "Kya owner ya sales head se baat ho sakti hai" in prompt
    assert "main samajh sakta hoon" in prompt and "main samajh sakti hoon" not in prompt


def test_build_prompt_strips_brackets_from_llm_text_and_repairs_welcome():
    prompt, welcome = _build(brief=_brief(
        opening_value_line="Hum [their industry] {x} companies ki madad karte hain.",
        welcome_message="Namaste [prospect name] ji",
    ))
    assert "Hum their industry x companies" in prompt
    assert welcome == "Namaste ji! Main Priya bol rahi hoon MOTM se."  # didn't name the agent → default


def _profile():
    from types import SimpleNamespace
    return SimpleNamespace(
        company_name="MOTM", website=None, industry=None, what_we_offer="Leads", value_proposition=None,
        target_customers=None, key_points=None, call_objective=None, tone_notes=None, extra_info=None,
    )


async def test_generate_builds_kit_once_and_brief_per_contact(fake_redis):
    from app.config import settings

    def fake_llm(**kwargs):
        result = prime_prompt._LLMResult(_kit() if kwargs["name"] == "campaign_kit" else _brief())
        result.web_searched = kwargs["name"] == "call_brief"
        return result

    llm = AsyncMock(side_effect=fake_llm)
    with patch.object(settings, "OPENAI_API_KEY", "sk-test"), patch.object(prime_prompt, "_generate_json", llm):
        first = await prime_prompt.generate_contact_prompt(
            profile=_profile(), base_prompt="BASE", language="hinglish", contact=_contact(),
        )
        await prime_prompt.generate_contact_prompt(
            profile=_profile(), base_prompt="BASE", language="hinglish", contact=_contact(),
        )
    jobs = [c.kwargs["name"] for c in llm.await_args_list]
    assert jobs == ["campaign_kit", "call_brief", "call_brief"]  # kit cached in Redis
    assert first.web_searched and "Chakan" in first.system_prompt
    brief_call = llm.await_args_list[1].kwargs
    assert brief_call["web_search"] is True
    assert "<contact_data>" in brief_call["user"] and "name: Ravi" in brief_call["user"]


async def test_generate_json_falls_back_from_openai_to_groq():
    from app.config import settings

    openai = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock(return_value=prime_prompt._LLMResult({"ok": 1}))
    with patch.object(settings, "OPENAI_API_KEY", "sk-test"), patch.object(settings, "GROQ_API_KEY", "gsk"), \
            patch.object(prime_prompt, "_call_openai", openai), patch.object(prime_prompt, "_call_groq", groq):
        result = await prime_prompt._generate_json(instructions="I", user="U", name="call_brief",
                                                   schema={}, web_search=True)
    assert result == {"ok": 1} and openai.await_count == 2 and groq.await_count == 1


async def test_call_openai_reads_responses_output():
    import json

    from app.config import settings

    payload = {"status": "completed", "output": [
        {"type": "reasoning"},
        {"type": "web_search_call", "action": {"type": "search"}},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"a": "b"})}]},
    ]}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return payload

    post = AsyncMock(return_value=_Resp())
    with patch.object(settings, "OPENAI_API_KEY", "sk-test"), \
            patch.object(prime_prompt.httpx.AsyncClient, "post", post):
        result = await prime_prompt._call_openai(instructions="I", user="U", name="call_brief",
                                                 schema={"type": "object"}, web_search=True)
    assert result == {"a": "b"} and result.web_searched
    body = post.await_args.kwargs["json"]
    assert body["model"] == settings.PRIME_OPENAI_MODEL
    assert body["tools"][0]["type"] == "web_search"
    assert body["text"]["format"]["type"] == "json_schema"


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


def test_spoken_strips_web_search_citations_and_labels():
    raw = ("Bharat Forge has 18 plants. ([bharatforge.com](https://www.bharatforge.com/AR2025/"
           "index.html?utm_source=openai))")
    assert prime_prompt._spoken(raw) == "Bharat Forge has 18 plants."
    assert prime_prompt._spoken("Hypothesis: Long sales cycles") == "Long sales cycles"
    assert prime_prompt._spoken("See https://acme.com/about for more") == "See for more"


@pytest.mark.parametrize("mode,site_text,expected", [
    ("auto", "Acme makes gears", False),   # we read their site ourselves → no paid search
    ("auto", "", True),                     # nothing to read → search
    ("always", "Acme makes gears", True),
    ("never", "", False),
])
async def test_web_search_mode(mode, site_text, expected):
    from app.config import settings

    llm = AsyncMock(return_value=prime_prompt._LLMResult(_brief()))
    with patch.object(settings, "OPENAI_API_KEY", "sk-test"), patch.object(settings, "PRIME_WEB_SEARCH", mode), \
            patch.object(prime_prompt, "_generate_json", llm):
        await prime_prompt._get_brief(_kit(), _profile(), _contact(), "hinglish", site_text, "Namaste")
    assert llm.await_args.kwargs["web_search"] is expected


def test_spoken_tidies_space_before_punctuation():
    assert prime_prompt._spoken("Acme has 18 plants . Nice") == "Acme has 18 plants. Nice"
