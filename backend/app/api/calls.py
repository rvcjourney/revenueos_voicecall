from __future__ import annotations

from datetime import timedelta, timezone
from uuid import UUID

from urllib.parse import urlparse

import aiohttp
import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import TokenPayload, get_current_user, require_agent_webhook_signature
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.call import Call, CallDirection, CallOutcome, CallStatus, CallTranscript
from app.models.dnc import DNCReason, DoNotCallEntry
from app.schemas.call import CallDetail, CallListResponse, CallOut, TranscriptSegment

log = structlog.get_logger(__name__)
router = APIRouter()


def _is_trusted_vobiz_host(url: str) -> bool:
    """
    Only ever fetch/store recording URLs that actually point at Vobiz's own
    media domain (e.g. media.vobiz.ai) — recording_url is set from an
    unauthenticated-by-Vobiz-design webhook body, so without this check an
    attacker could plant an arbitrary URL there. When it's later proxy-fetched
    server-side (see proxy_recording below), the org's real Vobiz API
    credentials are sent along with the request — fetching an attacker-chosen
    host would leak them. Vobiz recordings are documented as served from
    media.vobiz.ai (see app/core/vobiz.py); any *.vobiz.ai host is accepted.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return bool(host) and (host == "vobiz.ai" or host.endswith(".vobiz.ai"))


def _to_out(c: Call) -> CallOut:
    return CallOut(
        id=str(c.id),
        campaign_id=str(c.campaign_id) if c.campaign_id else None,
        phone_number=c.phone_number,
        direction=c.direction,
        status=c.status,
        outcome=c.outcome,
        sentiment=c.sentiment,
        started_at=c.started_at,
        answered_at=c.answered_at,
        ended_at=c.ended_at,
        duration_seconds=c.duration_seconds,
        cost_inr=float(c.cost_inr) if c.cost_inr else None,
        summary=c.summary,
        recording_url=c.recording_url,
        created_at=c.created_at,
    )


def _to_detail(c: Call) -> CallDetail:
    segments = []
    if c.transcript:
        for seg in c.transcript.segments:
            segments.append(
                TranscriptSegment(
                    speaker=seg.get("speaker", ""),
                    text=seg.get("text", ""),
                    start_ms=seg.get("start_ms"),
                    end_ms=seg.get("end_ms"),
                )
            )
    return CallDetail(
        **_to_out(c).model_dump(),
        extracted_data=c.extracted_data,
        error_message=c.error_message,
        transcript_segments=segments,
        transcript_full_text=c.transcript.full_text if c.transcript else None,
    )


@router.get("", response_model=CallListResponse)
async def list_calls(
    campaign_id: UUID | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [Call.org_id == token.org_id]
    if campaign_id:
        filters.append(Call.campaign_id == campaign_id)
    if outcome:
        filters.append(Call.outcome == outcome)

    # Aggregates over the whole filtered set, not just the page `rows` below
    # ends up with (capped at `limit`) -- the frontend's summary stat cards
    # (Call History) previously computed these client-side from just the
    # fetched page, which silently capped "Total calls"/"Interested"/
    # "Avg. duration" at whatever the first `limit` (max 200) rows happened
    # to contain instead of the org's real totals.
    agg = (await db.execute(
        select(
            func.count(Call.id).label("total"),
            func.count(Call.id).filter(Call.outcome == "interested").label("interested"),
            func.avg(Call.duration_seconds).filter(Call.duration_seconds > 0).label("avg_duration"),
        ).where(*filters)
    )).one()

    rows = (
        await db.execute(
            select(Call).where(*filters).order_by(Call.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return CallListResponse(
        items=[_to_out(r) for r in rows],
        total=agg.total,
        interested_count=agg.interested,
        avg_duration_seconds=round(agg.avg_duration) if agg.avg_duration else 0,
    )


class AgentReportIn(BaseModel):
    outcome: str
    summary: str = ""
    transcript: list[dict] = []
    # Set by the agent when the TTS pipeline itself failed (e.g. both generate_reply()
    # and the say() fallback raised) — the call connected but the agent never actually
    # spoke. Distinguishes a genuine silent-system-failure from a normal conversation
    # outcome so it isn't misreported as e.g. "not_interested".
    error_message: str | None = None
    extracted_data: dict = {}


@router.post(
    "/{call_id}/agent-report",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_agent_webhook_signature)],
)
async def agent_report(
    call_id: UUID,
    body: AgentReportIn,
    db: AsyncSession = Depends(get_db),
):
    """Called by the voice agent after each call to set the real outcome and summary."""
    from app.models.campaign import Campaign

    valid_outcomes = {e.value for e in CallOutcome}
    outcome = body.outcome if body.outcome in valid_outcomes else "not_interested"

    # Log field names only (never values) for extracted_data -- caller_email/caller_phone
    # are PII and must not land in logs, but knowing *which* fields the agent sent lets us
    # tell "Groq/agent sent nothing" apart from "backend dropped it" without a DB query.
    log.info(
        "agent_report_received",
        call_id=str(call_id),
        outcome_in=body.outcome,
        outcome_used=outcome,
        has_summary=bool(body.summary),
        has_error_message=bool(body.error_message),
        transcript_turns=len(body.transcript),
        extracted_data_fields=sorted(body.extracted_data.keys()) if body.extracted_data else [],
    )

    # Fetch the call to get campaign_id before updating
    call_row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one_or_none()
    if call_row is None:
        log.warning("agent_report_call_not_found", call_id=str(call_id))

    values: dict = {"outcome": outcome, "summary": body.summary or None}
    if body.error_message:
        values["status"] = CallStatus.FAILED
        values["error_message"] = body.error_message[:2000]
    if body.extracted_data:
        values["extracted_data"] = body.extracted_data

    try:
        await db.execute(update(Call).where(Call.id == call_id).values(**values))
    except Exception as exc:
        # get_db() rolls back and re-raises on any exception out of this function, so this
        # log is purely to make the failure visible with call_id context -- it must not
        # swallow the error, otherwise the agent would see a fake 204 success and never
        # retry / persist to failed_reports.jsonl.
        log.error(
            "agent_report_db_write_failed",
            call_id=str(call_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    log.info(
        "agent_report_saved",
        call_id=str(call_id),
        outcome=outcome,
        extracted_data_written="extracted_data" in values,
    )

    # Atomically increment campaign interested_count when outcome is interested
    if outcome == "interested" and call_row and call_row.campaign_id:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == call_row.campaign_id)
            .values(interested_count=Campaign.interested_count + 1)
        )

    # A customer explicitly asking not to be called again must actually stop
    # future dials, not just get labeled — the dispatcher already checks
    # DoNotCallEntry before every call (app/workers/tasks/campaign.py), this is
    # the only thing that was missing: nothing ever populated it from here.
    # on_conflict_do_nothing because (org_id, phone_number) is unique and the
    # same number may already be on the list.
    if outcome == "do_not_call" and call_row:
        await db.execute(
            pg_insert(DoNotCallEntry)
            .values(
                org_id=call_row.org_id,
                phone_number=call_row.phone_number,
                reason=DNCReason.USER_REQUEST,
                source_call_id=call_row.id,
            )
            .on_conflict_do_nothing(index_elements=["org_id", "phone_number"])
        )

    if body.transcript:
        full_text = "\n".join(
            f"{'CUSTOMER' if m.get('role') == 'user' else 'AGENT'}: {m.get('text', '')}"
            for m in body.transcript
        )
        segments = [{"speaker": m.get("role", ""), "text": m.get("text", "")} for m in body.transcript]
        existing = (await db.execute(
            select(CallTranscript).where(CallTranscript.call_id == call_id)
        )).scalar_one_or_none()
        if existing:
            existing.segments = segments
            existing.full_text = full_text
        else:
            db.add(CallTranscript(call_id=call_id, segments=segments, full_text=full_text))

    # Inbound calls have no wrapping campaign/test-call Celery task to trigger
    # a recording fetch the way outbound does -- this report is the only
    # signal that the call has ended, so fetch the recording from here.
    if call_row and call_row.direction == CallDirection.INBOUND and call_row.sip_trunk_id:
        from app.workers.tasks.campaign import fetch_recording_for_inbound_call
        fetch_recording_for_inbound_call.apply_async(
            args=[str(call_id), str(call_row.sip_trunk_id)], queue="calls",
        )

    await db.commit()


@router.get("/{call_id}", response_model=CallDetail)
async def get_call(
    call_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Call)
        .where(Call.id == call_id, Call.org_id == token.org_id)
        .options(selectinload(Call.transcript))
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Call not found")
    return _to_detail(call)


@router.post("/{call_id}/fetch-recording", status_code=status.HTTP_200_OK)
async def fetch_recording(
    call_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually retry fetching a recording from Vobiz for a completed call.
    Returns {"found": true} if recording URL was saved, {"found": false} if not available yet.
    """
    result = await db.execute(
        select(Call).where(Call.id == call_id, Call.org_id == token.org_id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Call not found")

    from app.core.vobiz import fetch_recording_for_call, resolve_vobiz_credentials

    vobiz_creds = await resolve_vobiz_credentials(db, org_id=call.org_id, campaign_id=call.campaign_id)
    if not vobiz_creds:
        raise HTTPException(status_code=503, detail="Vobiz credentials not configured")
    vobiz_auth_id, vobiz_auth_token = vobiz_creds

    # Use a wide window (2 hours before call start) to avoid timezone/clock-skew issues
    called_after = (call.started_at - timedelta(hours=2)) if call.started_at else None
    if not called_after:
        raise HTTPException(status_code=422, detail="Call has no start time")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            url = await fetch_recording_for_call(
                http,
                auth_id=vobiz_auth_id,
                auth_token=vobiz_auth_token,
                to_number=call.phone_number,
                called_after=called_after.replace(tzinfo=timezone.utc) if called_after.tzinfo is None else called_after,
                retries=2,
                retry_delay=2.0,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="Could not reach Vobiz — try again in a moment")

    if url:
        await db.execute(update(Call).where(Call.id == call_id).values(recording_url=url))
        await db.commit()
        return {"found": True, "recording_url": url}

    return {"found": False}


@router.get("/{call_id}/recording")
async def proxy_recording(
    call_id: UUID,
    download: bool = Query(False),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy the Vobiz recording through the backend so the browser doesn't need auth headers."""
    result = await db.execute(
        select(Call).where(Call.id == call_id, Call.org_id == token.org_id)
    )
    call = result.scalar_one_or_none()
    if not call or not call.recording_url:
        raise NotFoundError("Recording not found")

    if not _is_trusted_vobiz_host(call.recording_url):
        # Should be unreachable — the webhook that sets recording_url validates
        # the same host allowlist before storing it — but this is the point
        # that would actually leak the org's Vobiz credentials to whatever host
        # is in the URL, so it gets its own independent check rather than
        # trusting that nothing upstream ever let a bad value through.
        log.error("recording_untrusted_host", call_id=str(call_id), recording_url=call.recording_url)
        raise NotFoundError("Recording not found")

    from app.core.vobiz import resolve_vobiz_credentials, resolve_vobiz_credentials_by_recording_url

    vobiz_creds = await resolve_vobiz_credentials_by_recording_url(
        db, org_id=call.org_id, recording_url=call.recording_url
    ) or await resolve_vobiz_credentials(db, org_id=call.org_id, campaign_id=call.campaign_id)
    if not vobiz_creds:
        raise HTTPException(status_code=503, detail="Vobiz credentials not configured")
    vobiz_auth_id, vobiz_auth_token = vobiz_creds

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            vobiz = await client.get(
                call.recording_url,
                headers={
                    "X-Auth-ID": vobiz_auth_id,
                    "X-Auth-Token": vobiz_auth_token,
                },
            )
    except Exception:
        raise HTTPException(status_code=502, detail="Could not fetch recording — Vobiz unreachable")

    content_type = vobiz.headers.get("content-type", "audio/wav")
    ext = "wav" if ".wav" in call.recording_url else "mp3"
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="call_{call_id}.{ext}"'

    return Response(content=vobiz.content, media_type=content_type, headers=headers)
