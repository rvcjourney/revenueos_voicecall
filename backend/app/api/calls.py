from __future__ import annotations

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.call import Call, CallOutcome, CallTranscript
from app.schemas.call import CallDetail, CallListResponse, CallOut, TranscriptSegment

router = APIRouter()


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
    q = select(Call).where(Call.org_id == token.org_id)
    if campaign_id:
        q = q.where(Call.campaign_id == campaign_id)
    if outcome:
        q = q.where(Call.outcome == outcome)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(
            q.order_by(Call.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return CallListResponse(items=[_to_out(r) for r in rows], total=total)


class AgentReportIn(BaseModel):
    outcome: str
    summary: str = ""
    transcript: list[dict] = []


@router.post("/{call_id}/agent-report", status_code=status.HTTP_204_NO_CONTENT)
async def agent_report(
    call_id: UUID,
    body: AgentReportIn,
    db: AsyncSession = Depends(get_db),
):
    """Called by the voice agent after each call to set the real outcome and summary."""
    from app.models.campaign import Campaign

    valid_outcomes = {e.value for e in CallOutcome}
    outcome = body.outcome if body.outcome in valid_outcomes else "not_interested"

    # Fetch the call to get campaign_id before updating
    call_row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one_or_none()

    await db.execute(
        update(Call)
        .where(Call.id == call_id)
        .values(outcome=outcome, summary=body.summary or None)
    )

    # Atomically increment campaign interested_count when outcome is interested
    if outcome == "interested" and call_row and call_row.campaign_id:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == call_row.campaign_id)
            .values(interested_count=Campaign.interested_count + 1)
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

    async with httpx.AsyncClient(verify=False, timeout=60) as client:
        vobiz = await client.get(
            call.recording_url,
            headers={
                "X-Auth-ID": settings.VOBIZ_AUTH_ID,
                "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            },
        )

    content_type = vobiz.headers.get("content-type", "audio/wav")
    ext = "wav" if ".wav" in call.recording_url else "mp3"
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="call_{call_id}.{ext}"'

    return Response(content=vobiz.content, media_type=content_type, headers=headers)
