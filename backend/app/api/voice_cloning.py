"""
app/api/voice_cloning.py — Premium-plan voice cloning API.

A Premium org member submits an audio sample; it's forwarded to ElevenLabs'
Voice Cloning API (app/core/elevenlabs_voice.py) and the returned voice_id is
stored as a ClonedVoice row. That voice_id can then be used as any
AgentTemplate.voice_id (with voice_provider="elevenlabs") — the plan-gating
check in app/core/plan_features.py enforces that only orgs whose plan allows
voice_cloning can reference it there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import aiohttp
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.elevenlabs_voice import ElevenLabsVoiceError, clone_voice, delete_voice
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.plan_features import is_voice_cloning_allowed
from app.database import get_db
from app.models.cloned_voice import ClonedVoice
from app.schemas.voice_cloning import ClonedVoiceListResponse, ClonedVoiceOut

router = APIRouter()


def _to_out(v: ClonedVoice) -> ClonedVoiceOut:
    return ClonedVoiceOut(
        id=str(v.id),
        name=v.name,
        elevenlabs_voice_id=v.elevenlabs_voice_id,
        status=v.status,
        created_at=v.created_at,
    )


@router.get("", response_model=ClonedVoiceListResponse)
async def list_cloned_voices(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ClonedVoice).where(
            ClonedVoice.org_id == token.org_id,
            ClonedVoice.deleted_at.is_(None),
        ).order_by(ClonedVoice.created_at.desc())
    )).scalars().all()
    return ClonedVoiceListResponse(items=[_to_out(v) for v in rows])


@router.post("", response_model=ClonedVoiceOut, status_code=201)
async def create_cloned_voice(
    name: str = Form(...),
    file: UploadFile = File(...),
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Submit a voice sample and create a custom ElevenLabs voice model for this org."""
    if not await is_voice_cloning_allowed(db, token.org_id):
        raise PermissionDeniedError("Your plan does not include voice cloning. Upgrade to Premium to use this feature.")

    sample_bytes = await file.read()

    try:
        async with aiohttp.ClientSession() as http:
            elevenlabs_voice_id = await clone_voice(
                http,
                api_key=settings.ELEVENLABS_API_KEY,
                name=name,
                sample_bytes=sample_bytes,
                sample_filename=file.filename or "sample.mp3",
                content_type=file.content_type or "audio/mpeg",
            )
    except ElevenLabsVoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cloned = ClonedVoice(
        org_id=token.org_id,
        created_by_id=token.user_id,
        name=name,
        elevenlabs_voice_id=elevenlabs_voice_id,
        sample_file_name=file.filename or "",
    )
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)
    return _to_out(cloned)


@router.delete("/{cloned_voice_id}", status_code=204)
async def delete_cloned_voice(
    cloned_voice_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cloned = await db.get(ClonedVoice, cloned_voice_id)
    if not cloned or cloned.org_id != token.org_id or cloned.deleted_at:
        raise NotFoundError("Cloned voice not found")

    cloned.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    async with aiohttp.ClientSession() as http:
        await delete_voice(http, api_key=settings.ELEVENLABS_API_KEY, voice_id=cloned.elevenlabs_voice_id)
