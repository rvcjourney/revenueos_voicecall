"""
app/core/sarvam_voice.py — Sarvam Instant Voice Cloning (beta): create and delete
a cloned voice. Endpoints and shapes from the sarvamai 0.1.37 SDK
(POST /voices/create multipart file+name+language -> {"status", "data":
{"voice_id": "svc-...", "status", "reference_text"}}; DELETE /voices/delete/{id}).

Off unless settings.SARVAM_VOICE_CLONING_ENABLED (the API key needs the
text_to_speech_voice_cloning capability). Retries 429/5xx with backoff, never
other 4xx; logs every request_id. Never logs the key or request headers.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

SARVAM_API_BASE = "https://api.sarvam.ai"
_RETRY_DELAYS = (1.0, 2.0, 4.0)


class SarvamVoiceError(Exception):
    def __init__(self, message: str, *, status: int | None = None, request_id: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id


class SarvamCloningDisabled(SarvamVoiceError):
    pass


def _request_id(resp: httpx.Response) -> str | None:
    try:
        body = resp.json()
        return body.get("request_id") or (body.get("error") or {}).get("request_id")
    except ValueError:
        return resp.headers.get("x-request-id")


async def _send(method: str, path: str, **kwargs) -> httpx.Response:
    if not settings.SARVAM_VOICE_CLONING_ENABLED or not settings.SARVAM_API_KEY:
        raise SarvamCloningDisabled("Sarvam voice cloning is not enabled on this platform yet.")
    headers = {"api-subscription-key": settings.SARVAM_API_KEY}
    async with httpx.AsyncClient(base_url=SARVAM_API_BASE, timeout=120.0) as http:
        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            resp = await http.request(method, path, headers=headers, **kwargs)
            rid = _request_id(resp)
            log.info("sarvam_voice_api", method=method, path=path.split("/svc-")[0], status=resp.status_code, request_id=rid)
            retryable = resp.status_code == 429 or resp.status_code >= 500
            if not retryable or delay is None:
                return resp
            await asyncio.sleep(delay)
    return resp  # pragma: no cover


async def create_voice(*, name: str, language: str, sample_bytes: bytes, filename: str, content_type: str) -> tuple[str, str | None]:
    """Returns (voice_id, reference_text). language = BCP-47 code of the clip."""
    resp = await _send(
        "POST", "/voices/create",
        data={"name": name[:100], "language": language},
        files={"file": (filename, sample_bytes, content_type)},
    )
    if resp.status_code >= 300:
        raise SarvamVoiceError(_error_message(resp), status=resp.status_code, request_id=_request_id(resp))
    data = resp.json().get("data") or {}
    if not str(data.get("voice_id", "")).startswith("svc-"):
        raise SarvamVoiceError("Unexpected response from the voice service", status=resp.status_code, request_id=_request_id(resp))
    return data["voice_id"], data.get("reference_text")


async def delete_voice(voice_id: str) -> None:
    resp = await _send("DELETE", f"/voices/delete/{voice_id}")
    if resp.status_code == 404:
        return  # already gone
    if resp.status_code >= 300:
        raise SarvamVoiceError(_error_message(resp), status=resp.status_code, request_id=_request_id(resp))


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return (body.get("error") or {}).get("message") or body.get("message") or f"HTTP {resp.status_code}"
    except ValueError:
        return f"HTTP {resp.status_code}"
