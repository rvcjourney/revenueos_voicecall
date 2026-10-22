"""
tests/test_pipelines.py — the calling engine (app/core/pipelines.py): language
registry, owner overrides, voice validation, per-call config, and the API
endpoints that use them.
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


# ── Registry ──────────────────────────────────────────────────────────────────
def test_registry_every_enabled_language_is_complete():
    for key, lang in p.LANGUAGES.items():
        assert lang.stt_code and lang.tts_code and lang.clone_code, key
        if p.language_enabled(key, ON):
            assert p.sarvam_voices(key, ON), key


def test_malayalam_and_odia_registered_but_disabled():
    for key in ("malayalam", "odia"):
        assert key in p.LANGUAGES
        assert not p.language_enabled(key, ON)
        with pytest.raises(p.PipelineValidationError):
            p.validate(key, None, ON)


def test_owner_override_enables_language_and_switches_model():
    s = p.OwnerSettings(language_overrides={"malayalam": {"sarvam": {"enabled": True}},
                                            "hindi": {"sarvam": {"tts_model": p.V3}}})
    assert p.language_enabled("malayalam", s)
    assert p.sarvam_tts_model("hindi", s) == p.V3
    assert "ritu" in {v.id for v in p.sarvam_voices("hindi", s)}  # v3 short names now valid


# ── Validation ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("language, voice, cloned", [
    ("hindi", None, False),
    ("hindi", "ritu_hi_conversation", False),
    ("tamil", "ritu", False),
    ("hindi", "svc-clone", True),
])
def test_valid_combinations(language, voice, cloned):
    p.validate(language, voice, ON, cloned=cloned)


@pytest.mark.parametrize("language, voice", [
    ("hinglish", "9BWtsMINqrJLrRacOk9x"),   # an old ElevenLabs voice
    ("tamil", "ritu_hi_conversation"),      # a voice from another language
    ("klingon", None),
])
def test_invalid_combinations_have_vendor_free_messages(language, voice):
    with pytest.raises(p.PipelineValidationError) as exc:
        p.validate(language, voice, ON)
    msg = str(exc.value).lower()
    for vendor in ("sarvam", "elevenlabs", "groq", "bulbul", "qwen"):
        assert vendor not in msg


def test_sarvam_call_config_carries_every_enabled_language():
    cfg = p.sarvam_call_config("hindi", None, ON, cloned=False)
    assert cfg["voice_id"] in {v.id for v in p.sarvam_voices("hindi", ON)}
    assert set(cfg["languages"]) == {k for k in p.LANGUAGES if p.language_enabled(k, ON)}
    assert cfg["languages"]["tamil"]["tts_model"] == p.V3


# ── Per-call config ───────────────────────────────────────────────────────────
async def _org_admin(db):
    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email=f"a-{uuid.uuid4().hex[:8]}@x.test", hashed_password=hash_password("pw-123456"),
                full_name="A", role=UserRole.ADMIN, is_active=True)
    db.add(user)
    await db.commit()
    p.invalidate_owner_settings()
    return org, {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}


async def test_call_meta_replaces_an_old_elevenlabs_voice_with_the_language_default(db):
    org, _ = await _org_admin(db)
    cfg = (await p.call_meta(db, org_id=org.id, language="hindi", voice_id="9BWtsMINqrJLrRacOk9x"))["sarvam"]
    assert cfg["voice_id"] == p.default_sarvam_voice("hindi", ON) and cfg["cloned"] is False


async def test_call_meta_uses_the_orgs_own_clone_only(db):
    org, _ = await _org_admin(db)
    other, _ = await _org_admin(db)
    db.add(ClonedVoice(org_id=org.id, name="Mine", elevenlabs_voice_id="svc-mine", provider="sarvam"))
    await db.commit()
    mine = (await p.call_meta(db, org_id=org.id, language="hindi", voice_id="svc-mine"))["sarvam"]
    assert (mine["voice_id"], mine["cloned"]) == ("svc-mine", True)
    theirs = (await p.call_meta(db, org_id=other.id, language="hindi", voice_id="svc-mine"))["sarvam"]
    assert theirs["cloned"] is False and theirs["voice_id"] != "svc-mine"


async def test_call_meta_falls_back_to_default_language_when_disabled(db):
    org, _ = await _org_admin(db)
    cfg = (await p.call_meta(db, org_id=org.id, language="malayalam", voice_id=None))["sarvam"]
    assert cfg["language"] == p.DEFAULT_LANGUAGE


# ── API ───────────────────────────────────────────────────────────────────────
async def test_languages_endpoint_follows_owner_overrides(client, db):
    _, h = await _org_admin(db)
    db.add(PlatformCostSettings(id=1, language_overrides={"tamil": {"sarvam": {"enabled": False}}}))
    await db.commit()
    p.invalidate_owner_settings()
    body = (await client.get("/api/languages", headers=h)).json()
    keys = {lang["value"] for lang in body["languages"]}
    assert "tamil" not in keys and "hindi" in keys
    assert body["cloning_allowed"] is False
    p.invalidate_owner_settings()


async def test_cloned_voice_isolation_between_orgs(client, db):
    other, _ = await _org_admin(db)
    db.add(ClonedVoice(org_id=other.id, name="Theirs", elevenlabs_voice_id="svc-theirs", provider="sarvam"))
    await db.commit()
    _, h = await _org_admin(db)
    r = await client.post("/api/agents", json={"name": "A", "language": "hindi", "voice_id": "svc-theirs"}, headers=h)
    assert r.status_code == 403


async def test_campaign_language_and_voice_are_validated(client, db):
    org, h = await _org_admin(db)
    tmpl = AgentTemplate(org_id=org.id, name="T", language="hindi")
    db.add(tmpl)
    await db.commit()
    ok = await client.post("/api/campaigns", json={"name": "C", "agent_template_id": str(tmpl.id),
                                                   "language": "tamil", "voice_id": "ritu"}, headers=h)
    assert ok.status_code == 201, ok.text
    dup = await client.post(f"/api/campaigns/{ok.json()['id']}/duplicate", headers=h)
    assert (dup.json()["language"], dup.json()["voice_id"]) == ("tamil", "ritu")
    bad = await client.post("/api/campaigns", json={"name": "D", "agent_template_id": str(tmpl.id),
                                                    "language": "tamil", "voice_id": "ritu_hi_conversation"}, headers=h)
    assert bad.status_code == 422
