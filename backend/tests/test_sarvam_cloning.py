"""
tests/test_sarvam_cloning.py — Indic Native (Sarvam) voice cloning: customer
request -> owner approval -> Sarvam voice, and deletion. Sarvam is always faked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core import sarvam_voice
from app.models.cloned_voice import ClonedVoice
from app.models.voice_clone_request import VoiceCloneRequest
from tests.test_premium_features import PREMIUM_FEATURES, _fake_storage, _make_org_and_admin, _make_platform_admin

FILES = {
    "file": ("sample.wav", b"fake-audio-bytes", "audio/wav"),
    "consent_video": ("consent.webm", b"fake-video-bytes", "video/webm"),
}


async def _sarvam_org(db, *, cloning: bool = True):
    org, user, token = await _make_org_and_admin(db, plan_features=PREMIUM_FEATURES)
    org.sarvam_pipeline_enabled = True
    org.sarvam_cloning_allowed = cloning
    await db.commit()
    return org, {"Authorization": f"Bearer {token}"}


async def _submit(client, h, **data):
    with patch("app.api.voice_cloning.get_storage", return_value=_fake_storage()):
        return await client.post("/api/voice-cloning", data={"name": "Priya", **data}, files=FILES, headers=h)


async def test_indic_native_request_needs_owner_permission_and_a_language(client, db):
    _, h = await _sarvam_org(db, cloning=False)
    r = await _submit(client, h, engine="sarvam", language="hindi")
    assert r.status_code == 403 and "sarvam" not in r.text.lower()

    _, h = await _sarvam_org(db)
    assert (await _submit(client, h, engine="sarvam")).status_code == 422
    r = await _submit(client, h, engine="sarvam", language="tamil")
    assert r.status_code == 201 and r.json()["engine"] == "sarvam" and r.json()["status"] == "pending"


async def test_nothing_is_created_on_sarvam_before_approval_and_flag_off_blocks_it(client, db):
    _, h = await _sarvam_org(db)
    fake_create = AsyncMock(return_value=("svc-1", "ref"))
    with patch("app.core.sarvam_voice.create_voice", new=fake_create):
        req_id = (await _submit(client, h, engine="sarvam", language="hindi")).json()["id"]
    fake_create.assert_not_awaited()

    _, ptoken = await _make_platform_admin(db)
    with patch("app.api.platform.get_storage", return_value=_fake_storage()):
        r = await client.post(f"/api/platform/voice-clone-requests/{req_id}/approve",
                              headers={"Authorization": f"Bearer {ptoken}"})
    assert r.status_code == 409  # SARVAM_VOICE_CLONING_ENABLED is off by default
    assert (await db.scalar(select(ClonedVoice))) is None


async def test_approval_creates_sarvam_voice_usable_only_by_its_org(client, db):
    org, h = await _sarvam_org(db)
    req_id = (await _submit(client, h, engine="sarvam", language="marathi")).json()["id"]
    _, ptoken = await _make_platform_admin(db)
    fake_create = AsyncMock(return_value=("svc-abc", "नमस्कार"))
    with patch("app.api.platform.get_storage", return_value=_fake_storage()), \
         patch("app.core.sarvam_voice.create_voice", new=fake_create):
        r = await client.post(f"/api/platform/voice-clone-requests/{req_id}/approve",
                              headers={"Authorization": f"Bearer {ptoken}"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["provider"] == "sarvam"
    assert fake_create.await_args.kwargs["language"] == "mr-IN"
    voice = await db.scalar(select(ClonedVoice).where(ClonedVoice.org_id == org.id))
    assert (voice.provider, voice.provider_voice_id, voice.language, voice.reference_text) == ("sarvam", "svc-abc", "marathi", "नमस्कार")
    listed = (await client.get("/api/voice-cloning", headers=h)).json()["items"]
    assert [v["engine"] for v in listed] == ["sarvam"]


async def test_unusable_sample_goes_back_to_customer(client, db):
    _, h = await _sarvam_org(db)
    req_id = (await _submit(client, h, engine="sarvam", language="hindi")).json()["id"]
    _, ptoken = await _make_platform_admin(db)
    bad = AsyncMock(side_effect=sarvam_voice.SarvamVoiceError("audio too short", status=400, request_id="r-1"))
    with patch("app.api.platform.get_storage", return_value=_fake_storage()), \
         patch("app.core.sarvam_voice.create_voice", new=bad):
        r = await client.post(f"/api/platform/voice-clone-requests/{req_id}/approve",
                              headers={"Authorization": f"Bearer {ptoken}"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert "10–15 second" in r.json()["rejection_reason"]


async def test_delete_removes_voice_from_sarvam_and_reference_audio(client, db):
    org, h = await _sarvam_org(db)
    voice = ClonedVoice(org_id=org.id, name="P", elevenlabs_voice_id="svc-del", provider="sarvam")
    db.add(voice)
    await db.flush()
    db.add(VoiceCloneRequest(org_id=org.id, name="P", provider="sarvam", status="approved", cloned_voice_id=voice.id,
                             audio_sample_key="audio/x/sample.wav", consent_video_key="video/x/c.webm"))
    await db.commit()
    storage = _fake_storage()
    fake_delete = AsyncMock()
    with patch("app.api.voice_cloning.get_storage", return_value=storage), \
         patch("app.core.sarvam_voice.delete_voice", new=fake_delete):
        r = await client.delete(f"/api/voice-cloning/{voice.id}", headers=h)
    assert r.status_code == 204
    fake_delete.assert_awaited_once_with("svc-del")
    deleted_keys = [c.args[1] for c in storage.delete.await_args_list]
    assert deleted_keys == ["audio/x/sample.wav"]  # consent video kept as proof


async def test_cap_of_two_is_shared_across_engines(client, db):
    org, h = await _sarvam_org(db)
    db.add(ClonedVoice(org_id=org.id, name="EL", elevenlabs_voice_id="el-1", provider="elevenlabs"))
    await db.commit()
    assert (await _submit(client, h, engine="sarvam", language="hindi")).status_code == 201
    assert (await _submit(client, h, engine="sarvam", language="hindi")).status_code == 409


async def test_client_retries_429_and_5xx_but_not_other_4xx(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "SARVAM_VOICE_CLONING_ENABLED", True)
    monkeypatch.setattr(settings, "SARVAM_API_KEY", "k")
    monkeypatch.setattr(sarvam_voice, "_RETRY_DELAYS", (0, 0, 0))
    import httpx
    calls = []

    def responder(statuses):
        it = iter(statuses)

        def handler(request):
            calls.append(request.url.path)
            code = next(it)
            body = {"data": {"voice_id": "svc-ok", "status": "ready"}} if code == 200 else {"error": {"message": "x", "request_id": "r"}}
            return httpx.Response(code, json=body)
        return handler

    real_client = httpx.AsyncClient
    for statuses, expect_calls, ok in (([429, 503, 200], 3, True), ([400], 1, False)):
        calls.clear()
        monkeypatch.setattr(sarvam_voice.httpx, "AsyncClient",
                            lambda **kw: real_client(transport=httpx.MockTransport(responder(statuses)), **kw))
        try:
            vid, _ = await sarvam_voice.create_voice(name="n", language="hi-IN", sample_bytes=b"x", filename="a.wav", content_type="audio/wav")
            assert ok and vid == "svc-ok"
        except sarvam_voice.SarvamVoiceError as exc:
            assert not ok and exc.status == 400
        assert len(calls) == expect_calls
