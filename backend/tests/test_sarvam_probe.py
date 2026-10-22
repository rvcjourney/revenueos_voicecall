"""tests/test_sarvam_probe.py — the daily Sarvam model probe (fake Sarvam, fake Redis)."""
from __future__ import annotations

import base64
import json

import httpx

from app.workers.tasks import sarvam_probe

WAV = base64.b64encode(b"RIFF....WAVEfmt ").decode()


def _fake_sarvam(retired: set[str]):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = request.content.decode(errors="ignore")
        seen.append(path)
        if path == "/v1/chat/completions":
            if "llm" in retired:
                return httpx.Response(404, json={"error": {"message": "sarvam-105b-conversations has been deprecated."}})
            assert json.loads(body)["reasoning_effort"] is None  # thinking off
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        if path == "/text-to-speech":
            model = json.loads(body)["model"]
            if model in retired:
                return httpx.Response(400, json={"error": {"message": f"Model '{model}' has been deprecated."}})
            return httpx.Response(200, json={"audios": [WAV]})
        if path == "/speech-to-text":
            return httpx.Response(200, json={"transcript": "नमस्ते"})
        return httpx.Response(404)
    return handler, seen


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(sarvam_probe.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


async def test_probe_all_ok_records_last_ok(monkeypatch, fake_redis):
    handler, seen = _fake_sarvam(set())
    _patch_client(monkeypatch, handler)
    stored = await sarvam_probe._probe_and_store()
    assert stored["errors"] == {} and set(stored["ok"]) == {"llm", "tts_v4_flash", "tts_v3", "stt"}
    assert set(stored["last_ok_at"]) == {"llm", "tts_v4_flash", "tts_v3", "stt"}
    assert seen.count("/text-to-speech") == 2


async def test_probe_flags_a_retired_model_and_alerts(monkeypatch, fake_redis):
    sent = []
    import sentry_sdk
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda msg, level=None: sent.append(msg))
    handler, _ = _fake_sarvam({"bulbul:v3", "llm"})
    _patch_client(monkeypatch, handler)
    stored = await sarvam_probe._probe_and_store()
    assert stored["ok"] == {"llm": False, "tts_v4_flash": True, "tts_v3": False, "stt": True}
    assert "deprecated" in stored["errors"]["tts_v3"]
    assert len(sent) == 1 and "tts_v3" in sent[0]
