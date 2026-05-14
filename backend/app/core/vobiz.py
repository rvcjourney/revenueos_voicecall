"""
app/core/vobiz.py — Vobiz CDR and Recording API helpers.

Used after each outbound call to fetch the recording URL so it can be
stored in the Call record and shown in the UI.

Auth: X-Auth-ID + X-Auth-Token headers (from Vobiz console → dashboard).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import aiohttp
import structlog

log = structlog.get_logger(__name__)

_BASE = "https://api.vobiz.ai/api/v1"


def _headers(auth_id: str, auth_token: str) -> dict[str, str]:
    return {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }


async def find_vobiz_call_uuid(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    to_number: str,
    called_after: datetime,
) -> str | None:
    """
    Search recent CDR for an outbound call to `to_number` placed after
    `called_after`. Returns the Vobiz call_uuid, or None if not found.
    """
    hdrs = _headers(auth_id, auth_token)
    norm_to = to_number.lstrip("+")

    try:
        async with http.get(
            f"{_BASE}/Account/{auth_id}/cdr/recent",
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                log.warning("vobiz_cdr_error", status=resp.status)
                return None
            data = await resp.json(content_type=None)

        records = data.get("objects") or data.get("calls") or data.get("data") or []
        for rec in records:
            to = (rec.get("to_number") or rec.get("to") or "").lstrip("+")
            direction = rec.get("call_direction") or rec.get("direction") or ""
            if direction and "outbound" not in direction.lower():
                continue
            if norm_to in to or to in norm_to:
                init_time_str = rec.get("initiation_time") or rec.get("start_time") or ""
                if init_time_str:
                    try:
                        # Vobiz returns "yyyy-MM-dd HH:mm:ss" format
                        init_time = datetime.strptime(init_time_str[:19], "%Y-%m-%d %H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        if init_time < called_after - timedelta(minutes=5):
                            continue  # too old — not our call
                    except ValueError:
                        pass
                call_uuid = rec.get("call_uuid") or rec.get("uuid") or ""
                if call_uuid:
                    return call_uuid

    except asyncio.TimeoutError:
        log.warning("vobiz_cdr_timeout")
    except Exception as exc:
        log.warning("vobiz_cdr_failed", error=str(exc))

    return None


async def get_recording_url_for_call(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    call_uuid: str,
) -> str | None:
    """
    Fetch the recording download URL for a specific Vobiz call_uuid.
    Returns the direct HTTPS URL to the MP3, or None.
    """
    hdrs = _headers(auth_id, auth_token)

    try:
        async with http.get(
            f"{_BASE}/Account/{auth_id}/Recording/",
            headers=hdrs,
            params={"call_uuid": call_uuid},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                log.warning("vobiz_recording_error", status=resp.status, call_uuid=call_uuid)
                return None
            data = await resp.json(content_type=None)

        recordings = data.get("objects") or data.get("recordings") or data.get("data") or []
        if not recordings:
            return None

        rec = recordings[0]
        url = (
            rec.get("record_url")
            or rec.get("recording_url")
            or rec.get("url")
            or rec.get("download_url")
        )
        return url or None

    except asyncio.TimeoutError:
        log.warning("vobiz_recording_timeout", call_uuid=call_uuid)
    except Exception as exc:
        log.warning("vobiz_recording_failed", call_uuid=call_uuid, error=str(exc))

    return None


async def fetch_recording_for_call(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    to_number: str,
    called_after: datetime,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> str | None:
    """
    High-level helper: find Vobiz call_uuid via CDR, then get recording URL.
    Retries a few times because recordings take a few seconds to process.
    """
    for attempt in range(retries):
        if attempt > 0:
            await asyncio.sleep(retry_delay)

        call_uuid = await find_vobiz_call_uuid(
            http,
            auth_id=auth_id,
            auth_token=auth_token,
            to_number=to_number,
            called_after=called_after,
        )
        if not call_uuid:
            log.debug("vobiz_cdr_no_match", attempt=attempt, to=to_number)
            continue

        url = await get_recording_url_for_call(
            http,
            auth_id=auth_id,
            auth_token=auth_token,
            call_uuid=call_uuid,
        )
        if url:
            log.info("vobiz_recording_found", call_uuid=call_uuid, attempt=attempt)
            return url

        log.debug("vobiz_recording_not_ready_yet", call_uuid=call_uuid, attempt=attempt)

    return None
