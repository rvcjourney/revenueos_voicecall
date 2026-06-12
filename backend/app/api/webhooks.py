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

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call import Call

log = logging.getLogger(__name__)
router = APIRouter()


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
        call_uuid  = str(form.get("CallUUID")  or form.get("call_uuid")  or "")
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
