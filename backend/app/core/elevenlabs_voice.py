"""
app/core/elevenlabs_voice.py — ElevenLabs Voice Cloning API client.

Distinct from the ElevenLabs *TTS* integration used at call time (that lives
in the separate `agent/` LiveKit service via the `livekit-plugins-elevenlabs`
SDK, selected per-call by voice_provider — see agent/agent.py). Voice cloning
is a one-time REST call made from the backend when a Premium org member
submits a voice sample (app/api/voice_cloning.py); the resulting voice_id is
then usable as any AgentTemplate.voice_id with voice_provider="elevenlabs".

API reference: https://elevenlabs.io/docs/api-reference/voices/add
"""
from __future__ import annotations

import aiohttp
import structlog

log = structlog.get_logger(__name__)

_BASE = "https://api.elevenlabs.io/v1"

# ElevenLabs enforces limits on sample size/format; reject obviously-bad
# uploads before spending an API call.
MAX_SAMPLE_BYTES = 25 * 1024 * 1024  # 25 MB


class ElevenLabsVoiceError(Exception):
    """Raised when the ElevenLabs Voice Cloning API rejects a request. Message is safe to show the caller."""


async def clone_voice(
    http: aiohttp.ClientSession,
    *,
    api_key: str,
    name: str,
    sample_bytes: bytes,
    sample_filename: str,
    content_type: str = "audio/mpeg",
) -> str:
    """
    Submit a voice sample to ElevenLabs' Add Voice (cloning) endpoint.
    Returns the new ElevenLabs voice_id. Raises ElevenLabsVoiceError on failure.
    """
    if not sample_bytes:
        raise ElevenLabsVoiceError("Voice sample is empty")
    if len(sample_bytes) > MAX_SAMPLE_BYTES:
        raise ElevenLabsVoiceError("Voice sample exceeds the 25 MB limit")

    form = aiohttp.FormData()
    form.add_field("name", name)
    form.add_field("files", sample_bytes, filename=sample_filename, content_type=content_type)

    try:
        async with http.post(
            f"{_BASE}/voices/add",
            data=form,
            headers={"xi-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status == 401:
                raise ElevenLabsVoiceError("Invalid ElevenLabs API key")
            if resp.status != 200:
                body = await resp.text()
                log.warning("elevenlabs_clone_voice_error", status=resp.status, body=body[:500])
                raise ElevenLabsVoiceError(
                    "ElevenLabs rejected the voice sample — check the audio format and try again"
                )
            data = await resp.json(content_type=None)
    except ElevenLabsVoiceError:
        raise
    except Exception as exc:
        log.warning("elevenlabs_clone_voice_failed", error=str(exc))
        raise ElevenLabsVoiceError("Could not reach ElevenLabs to create the voice model") from exc

    voice_id = data.get("voice_id")
    if not voice_id:
        raise ElevenLabsVoiceError("ElevenLabs did not return a voice_id")
    return voice_id


async def delete_voice(http: aiohttp.ClientSession, *, api_key: str, voice_id: str) -> None:
    """Best-effort delete on ElevenLabs — failures are logged, never raised."""
    try:
        async with http.delete(
            f"{_BASE}/voices/{voice_id}",
            headers={"xi-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status not in (200, 204, 404):
                log.warning("elevenlabs_delete_voice_error", status=resp.status, voice_id=voice_id)
    except Exception as exc:
        log.warning("elevenlabs_delete_voice_failed", error=str(exc), voice_id=voice_id)
