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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credits import reset_credit_period
from app.core.razorpay_client import RazorpayError, verify_webhook_signature
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


async def _find_call_by_phone(
    db: AsyncSession,
    to_number: str,
    since_minutes: int = 60,
) -> Call | None:
    """Look up the most recent Call to `to_number` within the last `since_minutes`."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    norm = to_number.lstrip("+")

    result = await db.execute(
        select(Call)
        .where(
            Call.phone_number.contains(norm[-10:]),  # last 10 digits
            Call.started_at >= cutoff,
        )
        .order_by(Call.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/vobiz/recording", include_in_schema=False)
async def vobiz_recording_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Vobiz sends this when a recording finishes processing.
    Body is application/x-www-form-urlencoded.
    Fields: RecordUrl, RecordingID, CallUUID, RecordingDuration, RecordingEndReason
    Always returns 200 — if we return 4xx/5xx Vobiz will retry endlessly.
    """
    try:
        form = await request.form()
        record_url = str(form.get("RecordUrl") or form.get("record_url") or "")
        to_number  = str(form.get("To")        or form.get("to")         or "")

        if not record_url:
            return {"status": "ignored", "reason": "no RecordUrl"}

        call = None
        if to_number:
            call = await _find_call_by_phone(db, to_number)

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
        return {"status": "error"}  # still 200 — prevents Vobiz retry storms


@router.post("/vobiz/hangup", include_in_schema=False)
async def vobiz_hangup_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Vobiz hangup callback — captures CallUUID into sip_call_id for later lookup.
    Fields: CallUUID, From, To, CallStatus, Event, Direction
    Always returns 200 — if we return 4xx/5xx Vobiz will retry endlessly.
    """
    try:
        form = await request.form()
        call_uuid = str(form.get("CallUUID") or form.get("call_uuid") or "")
        to_number = str(form.get("To")       or form.get("to")       or "")

        if not call_uuid or not to_number:
            return {"status": "ignored"}

        call = await _find_call_by_phone(db, to_number)
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
        return {"status": "error"}
