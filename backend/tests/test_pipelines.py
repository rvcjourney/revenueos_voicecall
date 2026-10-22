"""
tests/test_pipelines.py — calling engines (app/core/pipelines.py): registry,
resolution order, the validation matrix, and the API gating that uses them.
"""
from __future__ import annotations

import uuid

import pytest

from app.core import pipelines as p
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentTemplate
from app.models.cloned_voice import ClonedVoice
from app.models.platform_cost_settings import PlatformCostSettings
from app.models.user import Organization, User, UserRole

ON = p.OwnerSettings()


class _Org:
    def __init__(self, enabled: bool):
        self.sarvam_pipeline_enabled = enabled


# ── Registry ──────────────────────────────────────────────────────────────────
def test_registry_every_enabled_language_is_complete():
    for key, lang in p.LANGUAGES.items():
        assert lang.stt_code and lang.tts_code and lang.clone_code, key
        for pipeline in p.PIPELINES:
            if p.language_enabled(key, pipeline, ON) and pipeline == p.SARVAM:
                assert p.sarvam_voices(key, ON), key


def test_malayalam_and_odia_registered_but_disabled_everywhere():
    for key in ("malayalam", "odia"):
        assert key in p.LANGUAGES
        assert not p.language_enabled(key, p.STANDARD, ON)
        assert not p.language_enabled(key, p.SARVAM, ON)
        with pytest.raises(p.PipelineValidationError):
            p.validate(p.SARVAM, key, None, ON)


def test_owner_override_enables_language_and_switches_model():
    s = p.OwnerSettings(language_overrides={"malayalam": {"sarvam": {"enabled": True}},
                                            "hindi": {"sarvam": {"tts_model": p.V3}}})
    assert p.language_enabled("malayalam", p.SARVAM, s)
    assert p.sarvam_tts_model("hindi", s) == p.V3
    assert "ritu" in {v.id for v in p.sarvam_voices("hindi", s)}  # v3 short names now valid


# ── Resolution ────────────────────────────────────────────────────────────────
def test_resolution_order_campaign_over_agent_over_default():
    assert p.requested_pipeline("sarvam", "standard") == "sarvam"
    assert p.requested_pipeline(None, "sarvam") == "sarvam"
    assert p.requested_pipeline(None, None) == "standard"
    assert p.requested_pipeline("bogus", None) == "standard"


@pytest.mark.parametrize("settings, org_on, language, reason", [
    (p.OwnerSettings(global_enabled=False), True, "hindi", "global"),
    (ON, False, "hindi", "organisation"),
    (p.OwnerSettings(language_overrides={"tamil": {"sarvam": {"enabled": False}}}), True, "tamil", "language"),
])
def test_sarvam_falls_back_with_reason(settings, org_on, language, reason):
    r = p.resolve(None, "sarvam", _Org(org_on), language, settings)
    assert (r.pipeline, r.requested, r.off_reason) == ("standard", "sarvam", reason)


def test_sarvam_resolves_when_everything_on():
    r = p.resolve("sarvam", "standard", _Org(True), "hindi", ON)
    assert (r.pipeline, r.off_reason) == ("sarvam", None)


# ── Validation matrix ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("pipeline, language, voice, kw", [
    ("standard", "hinglish", "9BWtsMINqrJLrRacOk9x", {"voice_provider": "elevenlabs"}),
    ("standard", "tamil", "ritu", {"voice_provider": "sarvam"}),
    ("standard", "hindi", "el-clone", {"cloned_provider": "elevenlabs"}),
    ("sarvam", "hindi", "ritu_hi_conversation", {"voice_provider": "sarvam"}),
    ("sarvam", "hinglish", None, {}),
    ("sarvam", "tamil", "ritu", {"voice_provider": "sarvam"}),          # tamil defaults to bulbul:v3
    ("sarvam", "marathi", "svc-123", {"cloned_provider": "sarvam"}),
])
def test_valid_combinations(pipeline, language, voice, kw):
    p.validate(pipeline, language, voice, ON, **kw)


@pytest.mark.parametrize("pipeline, language, voice, kw", [
    ("sarvam", "hinglish", "9BWtsMINqrJLrRacOk9x", {"voice_provider": "elevenlabs"}),
    ("sarvam", "hindi", "el-clone", {"cloned_provider": "elevenlabs"}),
    ("standard", "hindi", "svc-123", {"cloned_provider": "sarvam"}),
    ("sarvam", "hindi", "ritu", {"voice_provider": "sarvam"}),                 # v3 name on v4-flash
    ("sarvam", "tamil", "vijay_ta_narration", {"voice_provider": "sarvam"}),  # v4 name on v3
    ("sarvam", "hindi", "kavitha_te_conversation", {"voice_provider": "sarvam"}),  # wrong language
    ("sarvam", "klingon", None, {}),
    ("bogus", "hindi", None, {}),
])
def test_invalid_combinations(pipeline, language, voice, kw):
    with pytest.raises(p.PipelineValidationError) as exc:
        p.validate(pipeline, language, voice, ON, **kw)
    msg = str(exc.value).lower()
    for vendor in ("sarvam", "elevenlabs", "groq", "bulbul", "qwen"):
        assert vendor not in msg


def test_sarvam_call_config_carries_every_enabled_language():
    cfg = p.sarvam_call_config("hindi", None, ON, cloned=False)
    assert cfg["voice_id"] in {v.id for v in p.sarvam_voices("hindi", ON)}
    assert set(cfg["languages"]) == {k for k in p.LANGUAGES if p.language_enabled(k, p.SARVAM, ON)}
    assert cfg["languages"]["tamil"]["tts_model"] == p.V3


# ── API ───────────────────────────────────────────────────────────────────────
async def _org_admin(db, *, sarvam: bool = False):
    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}", sarvam_pipeline_enabled=sarvam)
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email=f"a-{uuid.uuid4().hex[:8]}@x.test", hashed_password=hash_password("pw-123456"),
                full_name="A", role=UserRole.ADMIN, is_active=True)
    db.add(user)
    await db.commit()
    p.invalidate_owner_settings()
    return org, {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}


async def test_old_agent_payload_still_means_standard(client, db):
    _, h = await _org_admin(db)
    r = await client.post("/api/agents", json={"name": "A"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["pipeline"] == "standard"


async def test_sarvam_agent_rejected_when_org_flag_off(client, db):
    _, h = await _org_admin(db, sarvam=False)
    r = await client.post("/api/agents", json={"name": "A", "pipeline": "sarvam", "language": "hindi",
                                               "voice_provider": "sarvam", "voice_id": "ritu_hi_conversation"}, headers=h)
    assert r.status_code == 403
    assert "sarvam" not in r.text.lower()


async def test_sarvam_agent_accepted_when_org_flag_on(client, db):
    _, h = await _org_admin(db, sarvam=True)
    r = await client.post("/api/agents", json={"name": "A", "pipeline": "sarvam", "language": "hindi",
                                               "voice_provider": "sarvam", "voice_id": "ritu_hi_conversation"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["pipeline"] == "sarvam"
    bad = await client.post("/api/agents", json={"name": "B", "pipeline": "sarvam", "language": "hindi"}, headers=h)
    assert bad.status_code == 422  # default ElevenLabs voice isn't valid on Indic Native


async def test_cloned_voice_isolation_between_orgs(client, db):
    other, _ = await _org_admin(db, sarvam=True)
    db.add(ClonedVoice(org_id=other.id, name="Theirs", elevenlabs_voice_id="svc-theirs", provider="sarvam"))
    await db.commit()
    _, h = await _org_admin(db, sarvam=True)
    r = await client.post("/api/agents", json={"name": "A", "pipeline": "sarvam", "language": "hindi",
                                               "voice_provider": "sarvam", "voice_id": "svc-theirs"}, headers=h)
    assert r.status_code == 403


async def test_global_switch_hides_engine_and_languages_endpoint(client, db):
    _, h = await _org_admin(db, sarvam=True)
    r = await client.get("/api/languages/engines", headers=h)
    assert [e["label"] for e in r.json()["engines"]] == ["Standard", "Indic Native"]
    db.add(PlatformCostSettings(id=1, sarvam_pipeline_global_enabled=False))
    await db.commit()
    p.invalidate_owner_settings()
    r = await client.get("/api/languages/engines", headers=h)
    assert [e["value"] for e in r.json()["engines"]] == ["standard"]
    langs = (await client.get("/api/languages?pipeline=sarvam", headers=h)).json()["languages"]
    assert "malayalam" not in {l["value"] for l in langs}
    assert all(l["voices"] for l in langs)


async def test_campaign_duplicate_copies_pipeline(client, db):
    org, h = await _org_admin(db, sarvam=True)
    tmpl = AgentTemplate(org_id=org.id, name="T", pipeline="sarvam", language="hindi",
                         voice_provider="sarvam", voice_id="ritu_hi_conversation")
    db.add(tmpl)
    await db.commit()
    r = await client.post("/api/campaigns", json={"name": "C", "agent_template_id": str(tmpl.id), "pipeline": "sarvam"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["pipeline"] == "sarvam"
    dup = await client.post(f"/api/campaigns/{r.json()['id']}/duplicate", json={}, headers=h)
    assert dup.status_code in (200, 201), dup.text
    assert dup.json()["pipeline"] == "sarvam"


# ── Dial time (every call path goes through resolve_call_engine) ─────────────
async def test_dial_on_sarvam_sends_engine_config(db):
    from app.models.company_profile import OrgCompanyProfile
    org, _ = await _org_admin(db, sarvam=True)
    db.add(OrgCompanyProfile(org_id=org.id, company_name="Rahul Steel", industry="TMT bars"))
    await db.commit()
    e = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline=None, agent_pipeline="sarvam",
                                    language="hindi", voice_id="9BWtsMINqrJLrRacOk9x", voice_provider="elevenlabs")
    assert (e.pipeline, e.fallback, e.pause) == ("sarvam", False, False)
    cfg = e.meta["sarvam"]
    assert cfg["voice_id"] == p.default_sarvam_voice("hindi", ON)  # ElevenLabs voice not carried over
    assert cfg["stt_prompt"] == "Rahul Steel, TMT bars" and cfg["cloned"] is False
    assert cfg["languages"]["hindi"]["repeat_line"] and cfg["languages"]["tamil"]["failure_line"]


async def test_dial_falls_back_to_standard_when_org_flag_off(db):
    org, _ = await _org_admin(db, sarvam=False)
    e = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline="sarvam", agent_pipeline="standard",
                                    language="hindi", voice_id="ritu_hi_conversation", voice_provider="sarvam")
    assert (e.pipeline, e.fallback, e.pause, e.voice_id, e.voice_provider) == ("standard", True, False, "", "elevenlabs")
    assert e.meta == {"pipeline": "standard"}


async def test_dial_pauses_when_sarvam_clone_loses_its_engine(db):
    org, _ = await _org_admin(db, sarvam=False)
    db.add(ClonedVoice(org_id=org.id, name="Mine", elevenlabs_voice_id="svc-mine", provider="sarvam"))
    await db.commit()
    e = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline="sarvam", agent_pipeline=None,
                                    language="hindi", voice_id="svc-mine", voice_provider="sarvam")
    assert e.pause and e.pipeline == "standard"


async def test_standard_dial_is_untouched(db):
    org, _ = await _org_admin(db, sarvam=True)
    e = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline=None, agent_pipeline="standard",
                                    language="tamil", voice_id="9BWtsMINqrJLrRacOk9x", voice_provider="elevenlabs")
    assert (e.pipeline, e.fallback, e.voice_id, e.voice_provider) == ("standard", False, "9BWtsMINqrJLrRacOk9x", "elevenlabs")


async def test_test_call_on_indic_native_rejects_free_form_overrides(client, db):
    org, h = await _org_admin(db, sarvam=True)
    tmpl = AgentTemplate(org_id=org.id, name="T", pipeline="sarvam", language="hindi",
                         voice_provider="sarvam", voice_id="ritu_hi_conversation")
    db.add(tmpl)
    await db.commit()
    r = await client.post(f"/api/agents/{tmpl.id}/test-call",
                          json={"phone_number": "+919876543210", "llm_provider": "groq"}, headers=h)
    assert r.status_code == 422
    assert "groq" not in r.text.lower() and "sarvam" not in r.text.lower()
