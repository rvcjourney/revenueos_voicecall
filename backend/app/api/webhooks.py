"""
app/api/webhooks.py — Vobiz callback receiver.

Configure your Vobiz SIP trunk or application to POST to:
  https://your-backend.com/webhooks/vobiz/recording
  https://your-backend.com/webhooks/vobiz/hangup

When a recording finishes, Vobiz posts RecordUrl + CallUUID which we use
to update the Call record's recording_url in real-time (faster than CDR polling).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credits import reset_credit_period
from app.core.razorpay_client import RazorpayError, verify_webhook_signature
from app.core.security import verify_vobiz_webhook_token
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.call import Call
from app.models.subscription import Subscription
from app.models.user import Organization

log = logging.getLogger(__name__)
router = APIRouter()

_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _unix_to_datetime(value: int | None) -> datetime | None:
    return _UNIX_EPOCH + timedelta(seconds=value) if value else None


def _is_trusted_vobiz_host(url: str) -> bool:
    """
    Mirrors app/api/calls.py::_is_trusted_vobiz_host — kept as a separate copy
    (not imported) to avoid a webhooks->calls import for one small check.
    Vobiz webhooks carry no signature Vobiz itself guarantees on the body, so
    RecordUrl is otherwise attacker-controllable input; only ever accept a
    value that actually points at Vobiz's own media domain before it's stored
    and later fetched server-side with the org's real Vobiz credentials.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return bool(host) and (host == "vobiz.ai" or host.endswith(".vobiz.ai"))


async def _find_call_by_phone(
    db: AsyncSession,
    to_number: str,
    since_minutes: int = 60,
    *,
    sip_trunk_id: UUID | None = None,
) -> Call | None:
    """
    Look up the most recent Call to `to_number` within the last `since_minutes`.

    When sip_trunk_id is known (i.e. the webhook URL carried a verified `tid`,
    see _verify_trunk_token below), matching is scoped to that trunk's calls
    only — which also scopes it to one org, since a trunk belongs to exactly
    one org. Without it (legacy webhook URLs registered before per-trunk
    tokens existed), this falls back to the old global-by-phone-digits match,
    which can misattribute a recording between two orgs that call/receive the
    same number in the same hour; new trunks should be reconnected to pick up
    the scoped URL.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    norm = to_number.lstrip("+")

    q = select(Call).where(
        Call.phone_number.contains(norm[-10:]),  # last 10 digits
        Call.started_at >= cutoff,
    )
    if sip_trunk_id is not None:
        q = q.where(Call.sip_trunk_id == sip_trunk_id)

    result = await db.execute(q.order_by(Call.started_at.desc()).limit(1))
    return result.scalar_one_or_none()


def _verify_trunk_token(tid: str | None, wt: str | None) -> UUID | None:
    """
    Returns the trunk UUID if `tid`+`wt` are present and `wt` is the correct
    token for that trunk (see sign_vobiz_webhook_token / connect_vobiz in
    app/api/sip_trunks.py, which is what puts these on the URL registered with
    Vobiz). Returns None — not an error — when they're absent, since existing
    trunks connected before this was added still use the old un-parameterized
    URL; callers treat None as "fall back to the legacy unscoped match."
    """
    if not tid or not wt:
        return None
    try:
        trunk_id = UUID(tid)
    except ValueError:
        return None
    if not verify_vobiz_webhook_token(trunk_id, wt):
        return None
    return trunk_id


@router.post("/vobiz/recording", include_in_schema=False)
async def vobiz_recording_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tid: str | None = Query(None),
    wt: str | None = Query(None),
):
    """
    Vobiz sends this when a recording finishes processing.
    Body is application/x-www-form-urlencoded.
    Fields: RecordUrl, RecordingID, CallUUID, RecordingDuration, RecordingEndReason
    Always returns 200 — if we return 4xx/5xx Vobiz will retry endlessly.

    `tid`/`wt` (trunk id + its signed token) are appended to the URL we hand
    Vobiz at trunk-connection time (see connect_vobiz in app/api/sip_trunks.py)
    — Vobiz itself doesn't sign its webhook bodies, so this is what stands in
    for that: proves the request is landing on the URL we actually registered
    for this specific trunk, and scopes call-matching to it.
    """
    try:
        trunk_id = _verify_trunk_token(tid, wt)

        form = await request.form()
        record_url = str(form.get("RecordUrl") or form.get("record_url") or "")
        to_number  = str(form.get("To")        or form.get("to")         or "")

        if not record_url:
            return {"status": "ignored", "reason": "no RecordUrl"}

        if not _is_trusted_vobiz_host(record_url):
            # Never store a recording_url outside Vobiz's own domain -- it's
            # later fetched server-side with the org's real Vobiz API
            # credentials attached (see proxy_recording in app/api/calls.py).
            log.warning("vobiz_recording_webhook_untrusted_host record_url=%s", record_url)
            return {"status": "ignored", "reason": "untrusted host"}

        call = None
        if to_number:
            call = await _find_call_by_phone(db, to_number, sip_trunk_id=trunk_id)

        if call and not call.recording_url:
            await db.execute(
                update(Call)
                .where(Call.id == call.id)
                .values(recording_url=record_url)
            )
            await db.commit()

        return {"status": "ok"}
    except Exception:
        log.exception("vobiz_recording_webhook_error")
        await db.rollback()  # leave the session clean so get_db's own commit doesn't also fail
        return {"status": "error"}  # still 200 — prevents Vobiz retry storms


@router.post("/vobiz/hangup", include_in_schema=False)
async def vobiz_hangup_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tid: str | None = Query(None),
    wt: str | None = Query(None),
):
    """
    Vobiz hangup callback — captures CallUUID into sip_call_id for later lookup.
    Fields: CallUUID, From, To, CallStatus, Event, Direction
    Always returns 200 — if we return 4xx/5xx Vobiz will retry endlessly.

    See vobiz_recording_webhook above for what `tid`/`wt` are. This endpoint's
    URL isn't set automatically anywhere in this codebase (it's configured
    directly in the Vobiz dashboard/account settings) — append
    `?tid=<trunk_id>&wt=<token>` there using the values shown for each trunk
    in GET /api/sip-trunks to get the same per-trunk scoping.
    """
    try:
        trunk_id = _verify_trunk_token(tid, wt)

        form = await request.form()
        call_uuid = str(form.get("CallUUID") or form.get("call_uuid") or "")
        to_number = str(form.get("To")       or form.get("to")       or "")

        if not call_uuid or not to_number:
            return {"status": "ignored"}

        call = await _find_call_by_phone(db, to_number, sip_trunk_id=trunk_id)
        if call and not call.sip_call_id:
            await db.execute(
                update(Call)
                .where(Call.id == call.id)
                .values(sip_call_id=call_uuid)
            )
            await db.commit()

        return {"status": "ok"}
    except Exception:
        log.exception("vobiz_hangup_webhook_error")
        await db.rollback()  # leave the session clean so get_db's own commit doesn't also fail
        return {"status": "error"}  # still 200 — prevents Vobiz retry storms


# ── Razorpay ───────────────────────────────────────────────────────────────
# Unlike Vobiz's unsigned webhooks above (which must always return 200 or
# Vobiz retries endlessly), Razorpay signs every request and handles retries
# on its own -- a bad/missing signature is rejected with 401 here, which is
# the one legitimate case for this router to not return 200.

@router.post("/razorpay", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        verify_webhook_signature(raw_body, signature)
    except RazorpayError:
        log.warning("razorpay_webhook_bad_signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        log.exception("razorpay_webhook_bad_json")
        return {"status": "ignored"}

    event = payload.get("event", "")
    sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    provider_subscription_id = sub_entity.get("id")

    if not provider_subscription_id:
        return {"status": "ignored", "reason": "no subscription entity"}

    try:
        sub = await db.scalar(
            select(Subscription).where(
                Subscription.provider_subscription_id == provider_subscription_id,
                Subscription.deleted_at.is_(None),
            )
        )
        if not sub:
            log.warning("razorpay_webhook_unknown_subscription", provider_subscription_id=provider_subscription_id)
            return {"status": "ignored", "reason": "unknown subscription"}

        org = await db.get(Organization, sub.org_id)

        if sub_entity.get("customer_id"):
            sub.provider_customer_id = sub_entity["customer_id"]

        if event == "subscription.authenticated":
            # Mandate/authorization payment confirmed -- there can be a short
            # delay before Razorpay follows up with activated/charged, so this
            # unblocks the org immediately rather than leaving it suspended
            # while waiting on those.
            sub.status = "authenticated"
            if org:
                org.is_active = True

        elif event == "subscription.activated":
            sub.status = "active"
            if org:
                org.is_active = True

        elif event == "subscription.charged":
            sub.status = "active"
            sub.current_period_start = _unix_to_datetime(sub_entity.get("current_start"))
            sub.current_period_end = _unix_to_datetime(sub_entity.get("current_end"))
            if org:
                org.is_active = True
                await reset_credit_period(db, org)

        elif event in ("subscription.halted", "subscription.cancelled"):
            sub.status = "cancelled" if event == "subscription.cancelled" else "halted"
            if org:
                org.is_active = False

        elif event == "subscription.pending":
            # A charge attempt failed and Razorpay is retrying -- Razorpay's own
            # grace period, not yet a suspend-worthy failure (that's `halted`).
            sub.status = "pending"

        else:
            return {"status": "ignored", "reason": f"unhandled event {event}"}

        db.add(AuditLog(
            actor_type="system",
            actor_id=None,
            org_id=sub.org_id,
            action=f"razorpay.{event}",
            target_type="subscription",
            target_id=sub.id,
        ))
        await db.commit()
        return {"status": "ok"}
    except Exception:
        log.exception("razorpay_webhook_error")
        await db.rollback()  # leave the session clean so get_db's own commit doesn't also fail
        return {"status": "error"}
