"""
app/core/vobiz.py — Vobiz Recording + Numbers API helpers.

Queries the Recording API directly by to_number — skips CDR lookup because
Vobiz recordings appear in the Recording list ~1-2 minutes after the call ends
but CDR records can lag longer.

Auth: X-Auth-ID + X-Auth-Token headers (from Vobiz console → dashboard).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp
import structlog

log = structlog.get_logger(__name__)

_BASE = "https://api.vobiz.ai/api/v1"
_ACCOUNT_URL_RE = re.compile(r"/Account/([^/]+)/")


def _headers(auth_id: str, auth_token: str) -> dict[str, str]:
    return {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }


class VobizValidationError(Exception):
    """Base for Vobiz account/DID validation failures. Message is safe to show the caller."""


class VobizAuthError(VobizValidationError):
    """auth_id/auth_token are not valid Vobiz API credentials."""


class VobizDidNotOwnedError(VobizValidationError):
    """Credentials are valid, but `did` is not a phone number on this Vobiz account."""


class VobizNumberNotActiveError(VobizValidationError):
    """`did` is on the account but isn't live yet (blocked, not active, or pending Aadhaar verification)."""


async def validate_vobiz_account_and_did(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    did: str,
) -> None:
    """
    Confirm (auth_id, auth_token) are valid Vobiz API credentials AND that
    `did` (E.164) is a phone number owned by that Vobiz account.

    Raises VobizAuthError or VobizDidNotOwnedError on failure. Returns None
    (does not raise) on success.
    """
    hdrs = _headers(auth_id, auth_token)
    norm_did = did.lstrip("+")

    try:
        async with http.get(
            f"{_BASE}/Account/{auth_id}/numbers",
            headers=hdrs,
            params={"page": 1, "per_page": 100},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body_text = await resp.text()
            if resp.status in (401, 403):
                log.warning(
                    "vobiz_account_validate_auth_error",
                    status=resp.status,
                    url=str(resp.url),
                    body=body_text[:500],
                )
                raise VobizAuthError("Invalid Vobiz auth_id or auth_token")
            if resp.status != 200:
                log.warning(
                    "vobiz_account_validate_error",
                    status=resp.status,
                    url=str(resp.url),
                    body=body_text[:500],
                )
                raise VobizAuthError("Could not verify Vobiz credentials — try again")
            data = await resp.json(content_type=None)
    except VobizValidationError:
        raise
    except Exception as exc:
        log.warning("vobiz_account_validate_failed", error=str(exc))
        raise VobizAuthError("Could not reach Vobiz to verify credentials") from exc

    numbers = data.get("items") or []
    for n in numbers:
        num = str(n.get("e164") or "").lstrip("+")
        if num and (num == norm_did or norm_did in num or num in norm_did):
            if n.get("is_blocked"):
                raise VobizNumberNotActiveError(f"{did} is blocked on this Vobiz account")
            if n.get("status") and n["status"] != "active":
                raise VobizNumberNotActiveError(f"{did} is not active yet on Vobiz (status: {n['status']})")
            if n.get("aadhaar_verification_required") and not n.get("aadhaar_verified"):
                raise VobizNumberNotActiveError(
                    f"{did} requires Aadhaar verification on Vobiz before it can be used — "
                    "complete verification in the Vobiz console, then try again"
                )
            return

    raise VobizDidNotOwnedError(f"{did} is not a phone number on this Vobiz account")


class VobizTrunkCreateError(VobizValidationError):
    """Could not create an outbound trunk on the org's own Vobiz account."""


async def create_vobiz_outbound_trunk(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    did: str,
    webhook_url: str,
) -> str:
    """
    Create a dedicated outbound SIP trunk on the org's own Vobiz account, with
    call recording and the recording webhook pre-enabled in the same request —
    so a non-technical admin never has to open Vobiz's console to turn either
    on manually; self-serve "Connect your number" does it automatically.

    Returns the trunk's assigned SIP domain (e.g. "ae06f8a1.sip.vobiz.ai").
    Raises VobizTrunkCreateError on failure.
    """
    hdrs = _headers(auth_id, auth_token)
    try:
        async with http.post(
            f"{_BASE}/Account/{auth_id}/trunks",
            headers=hdrs,
            json={
                "name": f"motmvoice-{did.lstrip('+')}",
                "trunk_direction": "outbound",
                "transport": "tcp",
                "recording": True,
                "recording_webhook_enabled": True,
                "webhook_url": webhook_url,
                "webhook_method": "POST",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body_text = await resp.text()
            if resp.status not in (200, 201):
                log.warning("vobiz_trunk_create_error", status=resp.status, body=body_text[:500])
                raise VobizTrunkCreateError(f"Vobiz rejected outbound trunk creation (status {resp.status})")
            data = await resp.json(content_type=None)
    except VobizValidationError:
        raise
    except Exception as exc:
        log.warning("vobiz_trunk_create_failed", error=str(exc))
        raise VobizTrunkCreateError("Could not reach Vobiz to create the outbound trunk") from exc

    trunk_domain = data.get("trunk_domain")
    if not trunk_domain:
        raise VobizTrunkCreateError("Vobiz did not return a trunk domain")
    return trunk_domain


async def create_vobiz_inbound_trunk(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    did: str,
    inbound_destination: str,
) -> str:
    """
    Create an inbound SIP trunk on the org's own Vobiz account, routing calls
    to `inbound_destination` (this platform's LiveKit SIP hostname — the same
    value for every org; LiveKit itself disambiguates by number via each
    SIPInboundTrunkInfo.numbers list).

    Returns the trunk's id (used by assign_vobiz_number_to_trunk() below).
    Raises VobizTrunkCreateError on failure.
    """
    # Vobiz's docs are explicit that inbound_destination must be the bare
    # host ("xxx.sip.livekit.cloud"), not a "sip:" URI — a trunk created with
    # the prefix silently routes nowhere (calls to the DID fail as "invalid
    # number") even though everything else about the trunk looks correct.
    # Stripped here so a misconfigured LIVEKIT_SIP_HOSTNAME env var can't
    # reproduce that bug regardless of how the caller formats it.
    clean_destination = inbound_destination.removeprefix("sip:")

    hdrs = _headers(auth_id, auth_token)
    try:
        async with http.post(
            f"{_BASE}/Account/{auth_id}/trunks",
            headers=hdrs,
            json={
                "name": f"motmvoice-inbound-{did.lstrip('+')}",
                "trunk_direction": "inbound",
                "transport": "tcp",
                "inbound_destination": clean_destination,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body_text = await resp.text()
            if resp.status not in (200, 201):
                log.warning("vobiz_inbound_trunk_create_error", status=resp.status, body=body_text[:500])
                raise VobizTrunkCreateError(f"Vobiz rejected inbound trunk creation (status {resp.status})")
            data = await resp.json(content_type=None)
    except VobizValidationError:
        raise
    except Exception as exc:
        log.warning("vobiz_inbound_trunk_create_failed", error=str(exc))
        raise VobizTrunkCreateError("Could not reach Vobiz to create the inbound trunk") from exc

    trunk_id = data.get("trunk_id")
    if not trunk_id:
        raise VobizTrunkCreateError("Vobiz did not return a trunk id")
    return trunk_id


async def assign_vobiz_number_to_trunk(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    did: str,
    trunk_id: str,
) -> None:
    """Link `did` to `trunk_id` so inbound calls to that DID route through it."""
    hdrs = _headers(auth_id, auth_token)
    try:
        async with http.post(
            f"{_BASE}/Account/{auth_id}/numbers/{quote(did, safe='')}/assign",
            headers=hdrs,
            json={"trunk_group_id": trunk_id},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status not in (200, 204):
                body_text = await resp.text()
                log.warning("vobiz_assign_number_error", status=resp.status, body=body_text[:500])
                raise VobizTrunkCreateError(f"Vobiz rejected assigning {did} to the inbound trunk (status {resp.status})")
    except VobizValidationError:
        raise
    except Exception as exc:
        log.warning("vobiz_assign_number_failed", error=str(exc))
        raise VobizTrunkCreateError("Could not reach Vobiz to assign the number") from exc


async def unassign_vobiz_number(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    did: str,
) -> None:
    """Best-effort unassign on Vobiz — failures are logged, never raised, so tearing
    down inbound calling always succeeds locally even if Vobiz is unreachable.

    Verified against Vobiz's OpenAPI spec (https://vobiz.ai/openapi.json):
    there is no separate POST .../unassign endpoint — unassignment is
    DELETE on the same .../{phone_number}/assign path.
    """
    hdrs = _headers(auth_id, auth_token)
    try:
        async with http.delete(
            f"{_BASE}/Account/{auth_id}/numbers/{quote(did, safe='')}/assign",
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status not in (200, 204, 404):
                body_text = await resp.text()
                log.warning("vobiz_unassign_number_error", status=resp.status, body=body_text[:500])
    except Exception as exc:
        log.warning("vobiz_unassign_number_failed", error=str(exc))


async def delete_vobiz_trunk(
    http: aiohttp.ClientSession,
    *,
    auth_id: str,
    auth_token: str,
    trunk_id: str,
) -> None:
    """
    Delete an inbound (or outbound) trunk outright -- verified against Vobiz's
    real API docs (DELETE /Account/{auth_id}/trunks/{trunk_id} -> 204), unlike
    unassign_vobiz_number()'s guessed endpoint above. Used by inbound teardown
    so re-running setup doesn't leave an orphaned trunk still holding the DID
    (previously: unassign silently no-op'd, the old trunk lingered enabled
    with the number still attached, and the freshly-created replacement trunk
    got no number at all).

    Best-effort: failures are logged, never raised, so teardown always
    succeeds locally even if Vobiz is unreachable or the trunk is already gone.
    """
    hdrs = _headers(auth_id, auth_token)
    try:
        async with http.delete(
            f"{_BASE}/Account/{auth_id}/trunks/{trunk_id}",
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status not in (200, 204, 404):
                body_text = await resp.text()
                log.warning("vobiz_delete_trunk_error", status=resp.status, body=body_text[:500])
    except Exception as exc:
        log.warning("vobiz_delete_trunk_failed", error=str(exc))


async def resolve_vobiz_credentials(
    session,
    *,
    org_id,
    trunk_id=None,
    livekit_trunk_id: str | None = None,
    campaign_id=None,
) -> tuple[str, str] | None:
    """
    Resolve which Vobiz auth_id/auth_token to use for a recording lookup.

    Each org can self-serve connect its own Vobiz account (app/api/sip_trunks.py
    POST /connect-vobiz), storing that account's credentials on the SipTrunk row
    itself — so a single global credential pair can't fetch every org's
    recordings. Resolution order: explicit trunk_id -> campaign's assigned
    trunk -> matching livekit_trunk_id -> org's default trunk -> global
    settings.VOBIZ_AUTH_ID/VOBIZ_AUTH_TOKEN (legacy shared trunk, pre self-serve).
    Returns None if no credentials could be resolved at all.
    """
    from sqlalchemy import select

    from app.config import settings
    from app.models.campaign import Campaign
    from app.models.sip import SipTrunk

    trunk = None
    if trunk_id:
        trunk = await session.get(SipTrunk, trunk_id)
    if trunk is None and campaign_id:
        campaign = await session.get(Campaign, campaign_id)
        if campaign and campaign.sip_trunk_id:
            trunk = await session.get(SipTrunk, campaign.sip_trunk_id)
    if trunk is None and livekit_trunk_id:
        trunk = await session.scalar(
            select(SipTrunk).where(
                SipTrunk.org_id == org_id,
                SipTrunk.livekit_trunk_id == livekit_trunk_id,
            )
        )
    if trunk is None:
        trunk = await session.scalar(
            select(SipTrunk).where(
                SipTrunk.org_id == org_id,
                SipTrunk.is_default.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )

    if trunk and trunk.vobiz_auth_id and trunk.vobiz_auth_token:
        return trunk.vobiz_auth_id, trunk.vobiz_auth_token

    if settings.VOBIZ_AUTH_ID and settings.VOBIZ_AUTH_TOKEN:
        return settings.VOBIZ_AUTH_ID, settings.VOBIZ_AUTH_TOKEN
    return None


async def resolve_vobiz_credentials_by_recording_url(
    session, *, org_id, recording_url: str
) -> tuple[str, str] | None:
    """
    Resolve credentials from the Vobiz account id embedded in an already-saved
    recording URL (e.g. https://media.vobiz.ai/v1/Account/MA_xxx/Recording/yyy).

    Authoritative for playback/download: it names the exact account that owns
    the file, so it can't be thrown off by which trunk happens to be marked
    is_default (which caused test-call recordings to save fine but 401 on
    playback, since the browser-facing proxy had no way to know which of the
    org's several Vobiz accounts actually placed that call).
    """
    from sqlalchemy import select

    from app.models.sip import SipTrunk

    m = _ACCOUNT_URL_RE.search(recording_url)
    if not m:
        return None
    account_id = m.group(1)
    trunk = await session.scalar(
        select(SipTrunk).where(
            SipTrunk.org_id == org_id,
            SipTrunk.vobiz_auth_id == account_id,
        )
    )
    if trunk and trunk.vobiz_auth_id and trunk.vobiz_auth_token:
        return trunk.vobiz_auth_id, trunk.vobiz_auth_token
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
    Query Vobiz Recording API directly by to_number.
    Recordings appear ~1-2 min after the call — call this from a background
    task with an initial delay rather than immediately after the call ends.
    """
    hdrs = _headers(auth_id, auth_token)
    norm_to = to_number.lstrip("+")
    _LIMIT = 100

    async def _fetch_page(offset: int) -> tuple[list[dict], int | None]:
        async with http.get(
            f"{_BASE}/Account/{auth_id}/Recording/",
            headers=hdrs,
            params={"limit": _LIMIT, "offset": offset},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                log.warning("vobiz_recording_list_error", status=resp.status, offset=offset)
                return [], None
            data = await resp.json(content_type=None)
        recs = data.get("objects") or data.get("recordings") or data.get("data") or []
        total = (data.get("meta") or {}).get("total_count")
        return recs, total

    for attempt in range(retries):
        if attempt > 0:
            await asyncio.sleep(retry_delay)

        try:
            # Vobiz's Recording API has no to_number or date-range filter, and its
            # default sort order isn't documented — so once an account has more than
            # one page of recordings, our target could be on the first page OR the
            # last page depending which way it sorts. Check both: if the account has
            # more than _LIMIT recordings, also fetch the last page (computed from
            # meta.total_count), which is where a new recording will land if Vobiz
            # sorts oldest-first (the more common REST default).
            recordings, total_count = await _fetch_page(0)
            if total_count and total_count > _LIMIT:
                last_page, _ = await _fetch_page(max(0, total_count - _LIMIT))
                recordings = recordings + last_page

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
