"""
app/workers/tasks/sarvam_probe.py — daily check that every Sarvam model the
Indic Native engine depends on still answers.

Sarvam retired several models in October 2026 (sarvam-m, glm5.2, bulbul:v2)
with no notice reaching us; each surfaced first as a crashed live call. This
probe finds the next one first and alerts Sentry. Ops note: also subscribe to
Sarvam's changelog feed, https://docs.sarvam.ai/changelog.rss.

Cost: one ~10-token LLM reply, two one-word TTS requests and one ~2 s STT
request per day — well under ₹1/day. Results land in Redis for the /ops
health card (app/api/platform.py). Skipped when SARVAM_API_KEY isn't set.
"""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timezone

import httpx
import structlog

from app.config import settings
from app.core import pipelines
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

PROBE_REDIS_KEY = "motm:sarvam_probe"
_BASE = "https://api.sarvam.ai"


def _err(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = (body.get("error") or {}).get("message") or body.get("message") or ""
    except ValueError:
        msg = ""
    return f"HTTP {resp.status_code} {msg}".strip()[:300]


async def run_probe() -> dict:
    """One tiny real request per component. Returns {"ok": {...}, "errors": {...}}."""
    ok: dict[str, bool] = {}
    errors: dict[str, str] = {}
    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
    v4_voice = pipelines.LANGUAGES["hindi"].v4_voices[0].id
    async with httpx.AsyncClient(base_url=_BASE, headers=headers, timeout=30.0) as http:
        async def check(name: str, coro):
            try:
                resp = await coro
                ok[name] = resp.status_code < 300
                if not ok[name]:
                    errors[name] = _err(resp)
                return resp
            except Exception as exc:  # network error counts as a failure, not a crash
                ok[name], errors[name] = False, f"{type(exc).__name__}: {exc}"[:300]
                return None

        await check("llm", http.post("/v1/chat/completions", json={
            "model": pipelines.SARVAM_LLM_MODEL,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}],
            "max_tokens": 10, "reasoning_effort": None,
        }))
        v4 = await check("tts_v4_flash", http.post("/text-to-speech", json={
            "text": "नमस्ते", "target_language_code": "hi-IN", "model": pipelines.V4_FLASH,
            "speaker": v4_voice, "speech_sample_rate": 16000,
        }))
        await check("tts_v3", http.post("/text-to-speech", json={
            "text": "नमस्ते", "target_language_code": "hi-IN", "model": pipelines.V3, "speaker": "ritu",
        }))
        # STT: reuse the v4 audio just synthesised (no fixture file to ship).
        if v4 is not None and ok.get("tts_v4_flash"):
            wav = base64.b64decode(v4.json()["audios"][0])
            await check("stt", http.post(
                "/speech-to-text",
                files={"file": ("probe.wav", wav, "audio/wav")},
                data={"model": pipelines.SARVAM_STT_PROBE_MODEL, "language_code": "hi-IN"},
            ))
        else:
            ok["stt"], errors["stt"] = False, "skipped: no probe audio (TTS failed)"
    return {"ok": ok, "errors": errors}


async def _probe_and_store() -> dict:
    from app.core.redis import get_redis

    result = await run_probe()
    now = datetime.now(timezone.utc).isoformat()
    redis = await get_redis()
    previous = json.loads(await redis.get(PROBE_REDIS_KEY) or "{}")
    last_ok = dict(previous.get("last_ok_at") or {})
    for name, good in result["ok"].items():
        if good:
            last_ok[name] = now
    stored = {"checked_at": now, **result, "last_ok_at": last_ok}
    await redis.set(PROBE_REDIS_KEY, json.dumps(stored))
    if result["errors"]:
        log.error("sarvam_probe_failed", errors=result["errors"])
        try:
            import sentry_sdk
            sentry_sdk.capture_message(f"Sarvam probe failed: {sorted(result['errors'])}", level="error")
        except Exception:
            pass
    else:
        log.info("sarvam_probe_ok")
    return stored


@celery_app.task(name="app.workers.tasks.sarvam_probe.probe_sarvam_models", bind=True)
def probe_sarvam_models(self) -> None:
    if not settings.SARVAM_API_KEY:
        log.info("sarvam_probe_skipped_no_key")
        return
    asyncio.run(_probe_and_store())
