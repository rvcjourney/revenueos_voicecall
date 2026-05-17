"""
app/core/vobiz.py — Vobiz Recording API helper.

Queries the Recording API directly by to_number — skips CDR lookup because
Vobiz recordings appear in the Recording list ~1-2 minutes after the call ends
but CDR records can lag longer.

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
    Query Vobiz Recording API directly by to_number.
    Recordings appear ~1-2 min after the call — call this from a background
    task with an initial delay rather than immediately after the call ends.
    """
    hdrs = _headers(auth_id, auth_token)
    norm_to = to_number.lstrip("+")

    for attempt in range(retries):
        if attempt > 0:
            await asyncio.sleep(retry_delay)

        try:
            async with http.get(
                f"{_BASE}/Account/{auth_id}/Recording/",
                headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning("vobiz_recording_list_error", status=resp.status, attempt=attempt)
                    continue
                data = await resp.json(content_type=None)

            recordings = data.get("objects") or data.get("recordings") or data.get("data") or []

            for rec in recordings:
                rec_to = (rec.get("to_number") or "").lstrip("+")
                if not rec_to or not (norm_to in rec_to or rec_to in norm_to):
                    continue

                # Confirm this recording is from our call (not an older one)
                add_time_str = rec.get("add_time") or ""
                if add_time_str:
                    try:
                        add_time = datetime.fromisoformat(add_time_str)
                        if add_time.tzinfo is None:
                            add_time = add_time.replace(tzinfo=timezone.utc)
                        add_time_utc = add_time.astimezone(timezone.utc)
                        if add_time_utc < called_after - timedelta(minutes=5):
                            continue  # too old — not our call
                    except ValueError:
                        pass

                url = rec.get("recording_url") or rec.get("record_url") or rec.get("url")
                if url:
                    log.info("vobiz_recording_found", to=to_number, attempt=attempt)
                    return url

            log.debug("vobiz_recording_not_ready_yet", to=to_number, attempt=attempt)

        except asyncio.TimeoutError:
            log.warning("vobiz_recording_timeout", to=to_number, attempt=attempt)
        except Exception as exc:
            log.warning("vobiz_recording_failed", error=str(exc), to=to_number)

    return None
