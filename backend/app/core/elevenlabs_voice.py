"""
app/core/elevenlabs_voice.py — ElevenLabs Instant Voice Cloning for Hinglish voices:
create and delete a cloned voice (POST /v1/voices/add multipart name+files ->
{"voice_id"}; DELETE /v1/voices/{id}). Regional-language clones stay on Sarvam
(app/core/sarvam_voice.py). Off unless settings.ELEVENLABS_API_KEY is set. Never
logs the key or request headers.
"""
from __future__ import annotations

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsVoiceError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ElevenLabsCloningDisabled(ElevenLabsVoiceError):
    pass


async def _send(method: str, path: str, **kwargs) -> httpx.Response:
    if not settings.ELEVENLABS_API_KEY:
        raise ElevenLabsCloningDisabled("Hinglish voice cloning is not set up yet (ELEVENLABS_API_KEY in backend/.env).")
    async with httpx.AsyncClient(base_url=_BASE, timeout=120.0) as http:
        resp = await http.request(method, path, headers={"xi-api-key": settings.ELEVENLABS_API_KEY}, **kwargs)
    log.info("elevenlabs_voice_api", method=method, path=path.split("/voices/")[0] + "/voices", status=resp.status_code)
    return resp


async def create_voice(*, name: str, sample_bytes: bytes, filename: str, content_type: str) -> str:
    """Returns the new voice_id."""
    resp = await _send("POST", "/voices/add", data={"name": name[:100]},
                       files={"files": (filename, sample_bytes, content_type)})
    if resp.status_code >= 300:
        raise ElevenLabsVoiceError(_error_message(resp), status=resp.status_code)
    voice_id = (resp.json() or {}).get("voice_id")
    if not voice_id:
        raise ElevenLabsVoiceError("Unexpected response from the voice service", status=resp.status_code)
    return voice_id


async def delete_voice(voice_id: str) -> None:
    resp = await _send("DELETE", f"/voices/{voice_id}")
    if resp.status_code == 404:
        return  # already gone
    if resp.status_code >= 300:
        raise ElevenLabsVoiceError(_error_message(resp), status=resp.status_code)


def _error_message(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
        if isinstance(detail, dict):
            return detail.get("message") or detail.get("status") or f"HTTP {resp.status_code}"
        return str(detail or f"HTTP {resp.status_code}")
    except ValueError:
        return f"HTTP {resp.status_code}"
