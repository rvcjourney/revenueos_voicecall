"""
tests/test_hinglish_cloning.py — voices recorded in Hinglish are cloned on ElevenLabs and
offered only for Hinglish; every other language keeps Sarvam clones. Providers are faked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core import elevenlabs_voice
from app.core import pipelines as p
from app.models.cloned_voice import ClonedVoice
from app.models.voice_clone_request import VoiceCloneRequest
from tests.test_premium_features import _fake_storage, _make_platform_admin
from tests.test_sarvam_cloning import _sarvam_org, _submit


async def _approve(client, db, req_id, **patches):
    _, ptoken = await _make_platform_admin(db)
    with patch("app.api.platform.get_storage", return_value=_fake_storage()), \
         patch("app.core.elevenlabs_voice.create_voice", new=patches.get("eleven", AsyncMock(return_value="el-new"))), \
         patch("app.core.sarvam_voice.create_voice", new=patches.get("sarvam", AsyncMock(return_value=("svc-new", "ref")))):
        return await client.post(f"/api/platform/voice-clone-requests/{req_id}/approve",
                                 headers={"Authorization": f"Bearer {ptoken}"})


async def test_hinglish_sample_is_cloned_on_elevenlabs_and_listed_as_hinglish_only(client, db):
    org, h = await _sarvam_org(db)
    req_id = (await _submit(client, h, language="hinglish")).json()["id"]
    eleven, sarvam = AsyncMock(return_value="el-abc"), AsyncMock()
    r = await _approve(client, db, req_id, eleven=eleven, sarvam=sarvam)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["provider"] == "elevenlabs"
    eleven.assert_awaited_once()
    sarvam.assert_not_awaited()
    voice = await db.scalar(select(ClonedVoice).where(ClonedVoice.org_id == org.id))
    assert (voice.provider, voice.provider_voice_id, voice.language) == ("elevenlabs", "el-abc", "hinglish")
    listed = (await client.get("/api/voice-cloning", headers=h)).json()["items"]
    assert [(v["voice_id"], v["hinglish_only"]) for v in listed] == [("el-abc", True)]


async def test_other_languages_still_clone_on_sarvam(client, db):
    _, h = await _sarvam_org(db)
    req_id = (await _submit(client, h, language="hindi")).json()["id"]
    eleven = AsyncMock()
    r = await _approve(client, db, req_id, eleven=eleven)
    assert r.json()["provider"] == "sarvam"
    eleven.assert_not_awaited()
    listed = (await client.get("/api/voice-cloning", headers=h)).json()["items"]
    assert [v["hinglish_only"] for v in listed] == [False]


async def test_unusable_hinglish_sample_asks_for_a_longer_clip(client, db):
    _, h = await _sarvam_org(db)
    req_id = (await _submit(client, h, language="hinglish")).json()["id"]
    bad = AsyncMock(side_effect=elevenlabs_voice.ElevenLabsVoiceError("too short", status=400))
    r = await _approve(client, db, req_id, eleven=bad)
    assert r.json()["status"] == "rejected" and "1–2 minutes" in r.json()["rejection_reason"]


async def test_each_clone_is_offered_only_for_its_languages(client, db):
    org, h = await _sarvam_org(db)
    db.add_all([
        ClonedVoice(org_id=org.id, name="H", elevenlabs_voice_id="el-h", provider="elevenlabs", language="hinglish"),
        ClonedVoice(org_id=org.id, name="S", elevenlabs_voice_id="svc-s", provider="sarvam", language="hindi"),
    ])
    await db.commit()

    async def create(language, voice_id):
        return (await client.post("/api/agents", json={"name": "A", "language": language, "voice_id": voice_id},
                                  headers=h)).status_code

    assert await create("hinglish", "el-h") == 201
    assert await create("tamil", "el-h") == 422
    assert await create("hindi", "svc-s") == 201
    assert await create("hinglish", "svc-s") == 422


async def test_old_elevenlabs_clones_stay_hidden_and_free(client, db):
    org, h = await _sarvam_org(db)
    db.add(ClonedVoice(org_id=org.id, name="Old", elevenlabs_voice_id="el-old", provider="elevenlabs"))
    await db.commit()
    assert (await client.get("/api/voice-cloning", headers=h)).json()["items"] == []
    r = await client.post("/api/agents", json={"name": "A", "language": "hinglish", "voice_id": "el-old"}, headers=h)
    assert r.status_code == 422


async def test_hinglish_call_speaks_with_the_orgs_elevenlabs_clone(db):
    org, _ = await _sarvam_org(db)
    db.add(ClonedVoice(org_id=org.id, name="H", elevenlabs_voice_id="el-h", provider="elevenlabs", language="hinglish"))
    await db.commit()
    cfg = (await p.call_meta(db, org_id=org.id, language="hinglish", voice_id="el-h"))["sarvam"]
    assert (cfg["voice_id"], cfg["cloned"]) == ("el-h", False)
    hl = cfg["languages"]["hinglish"]
    assert hl["engine"] == p.ELEVENLABS and hl["voices"][0]["id"] == "el-h"
    # Same clone on a Tamil campaign: not offered there, so the language default speaks
    ta = (await p.call_meta(db, org_id=org.id, language="tamil", voice_id="el-h"))["sarvam"]
    assert ta["voice_id"] != "el-h"


async def test_deleting_a_hinglish_clone_removes_it_from_elevenlabs(client, db):
    org, h = await _sarvam_org(db)
    voice = ClonedVoice(org_id=org.id, name="H", elevenlabs_voice_id="el-del", provider="elevenlabs", language="hinglish")
    db.add(voice)
    await db.flush()
    db.add(VoiceCloneRequest(org_id=org.id, name="H", provider="elevenlabs", language="hinglish", status="approved",
                             cloned_voice_id=voice.id, audio_sample_key="audio/x/s.wav", consent_video_key="video/x/c.webm"))
    await db.commit()
    eleven_delete, sarvam_delete = AsyncMock(), AsyncMock()
    with patch("app.api.voice_cloning.get_storage", return_value=_fake_storage()), \
         patch("app.core.elevenlabs_voice.delete_voice", new=eleven_delete), \
         patch("app.core.sarvam_voice.delete_voice", new=sarvam_delete):
        assert (await client.delete(f"/api/voice-cloning/{voice.id}", headers=h)).status_code == 204
    eleven_delete.assert_awaited_once_with("el-del")
    sarvam_delete.assert_not_awaited()
