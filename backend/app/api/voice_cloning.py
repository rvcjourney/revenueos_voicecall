"""
app/api/voice_cloning.py — Premium-plan voice cloning API.

A Premium org member submits an audio sample + a consent video (proof they're
authorized to clone that voice); this creates a VoiceCloneRequest in
"pending" status — no ElevenLabs call happens yet. A platform superadmin
reviews the video at /ops/voice-clone-requests (app/api/platform.py) and
either approves it (which THEN calls ElevenLabs' Voice Cloning API and
creates the real ClonedVoice row) or rejects it with a reason the org admin
can see here. Only an approved request's voice_id can ever be used as an
AgentTemplate.voice_id — the plan-gating check in app/core/plan_features.py
enforces that only orgs whose plan allows voice_cloning can reference it there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import aiohttp
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.config import settings
from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.elevenlabs_voice import MAX_SAMPLE_BYTES, delete_voice
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.plan_features import (
    MAX_CLONED_VOICES_PER_ORG,
    has_voice_clone_capacity,
    is_voice_cloning_allowed,
    is_voice_provider_allowed,
)
from app.database import get_db
from app.models.agent import VoiceProvider
from app.models.cloned_voice import ClonedVoice
from app.models.voice_clone_request import VoiceCloneRequest
from app.schemas.voice_cloning import ClonedVoiceListResponse, ClonedVoiceOut
from app.storage.backend import get_storage

log = structlog.get_logger(__name__)
router = APIRouter()

# Consent videos are a short fixed-script recording, not a large media file —
# 200 MB comfortably covers a webcam clip of any reasonable length while still
# rejecting obviously-wrong uploads before they're written to storage.
MAX_CONSENT_VIDEO_BYTES = 200 * 1024 * 1024


def _voice_out(v: ClonedVoice) -> ClonedVoiceOut:
    return ClonedVoiceOut(
        id=str(v.id),
        name=v.name,
        elevenlabs_voice_id=v.elevenlabs_voice_id,
        status=v.status,
        created_at=v.created_at,
    )


def _request_out(r: VoiceCloneRequest) -> ClonedVoiceOut:
    return ClonedVoiceOut(
        id=str(r.id),
        name=r.name,
        elevenlabs_voice_id=None,
        status=r.status,
        rejection_reason=r.rejection_reason,
        created_at=r.created_at,
    )


@router.get("", response_model=ClonedVoiceListResponse)
async def list_cloned_voices(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    voices = (await db.execute(
        select(ClonedVoice).where(
            ClonedVoice.org_id == token.org_id,
            ClonedVoice.deleted_at.is_(None),
        )
    )).scalars().all()

    # Approved requests already have a corresponding ClonedVoice row (created
    # at approval time) — only surface pending/rejected ones here, otherwise
    # every approved voice would show up twice.
    requests = (await db.execute(
        select(VoiceCloneRequest).where(
            VoiceCloneRequest.org_id == token.org_id,
            VoiceCloneRequest.status.in_(("pending", "rejected")),
        )
    )).scalars().all()

    items = [_voice_out(v) for v in voices] + [_request_out(r) for r in requests]
    items.sort(key=lambda i: i.created_at, reverse=True)
    return ClonedVoiceListResponse(items=items)


@router.post("", response_model=ClonedVoiceOut, status_code=201)
async def create_voice_clone_request(
    name: str = Form(...),
    file: UploadFile = File(...),
    consent_video: UploadFile = File(...),
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Submit a voice sample + consent video for superadmin review. Does not
    call ElevenLabs — that only happens once the request is approved."""
    if not await is_voice_cloning_allowed(db, token.org_id):
        raise PermissionDeniedError("Your plan does not include voice cloning. Upgrade to Premium to use this feature.")
    if not await is_voice_provider_allowed(db, token.org_id, VoiceProvider.ELEVENLABS):
        raise PermissionDeniedError("Voice cloning is currently disabled for your organization.")
    if not await has_voice_clone_capacity(db, token.org_id):
        raise ConflictError(
            f"Maximum limit for cloned voices is {MAX_CLONED_VOICES_PER_ORG}. Delete one of your existing "
            "voices, then try cloning again."
        )

    sample_bytes = await file.read()
    if not sample_bytes:
        raise HTTPException(status_code=422, detail="Voice sample is empty")
    if len(sample_bytes) > MAX_SAMPLE_BYTES:
        raise HTTPException(status_code=422, detail="Voice sample exceeds the 25 MB limit")

    video_bytes = await consent_video.read()
    if not video_bytes:
        raise HTTPException(status_code=422, detail="Consent video is empty")
    if len(video_bytes) > MAX_CONSENT_VIDEO_BYTES:
        raise HTTPException(status_code=422, detail="Consent video exceeds the 200 MB limit")

    request_id = uuid7()
    storage = get_storage()
    audio_key = f"audio/{token.org_id}/{request_id}/{file.filename or 'sample'}"
    video_key = f"video/{token.org_id}/{request_id}/{consent_video.filename or 'consent'}"
    await storage.upload(
        settings.BUCKET_VOICE_CONSENT, audio_key, sample_bytes, content_type=file.content_type or "audio/mpeg"
    )
    try:
        await storage.upload(
            settings.BUCKET_VOICE_CONSENT, video_key, video_bytes, content_type=consent_video.content_type or "video/webm"
        )
    except Exception:
        # The audio file already landed in storage but no DB row will ever
        # reference it — clean it up rather than leaving it orphaned. Best
        # effort: if the delete itself fails, log it for manual cleanup
        # instead of masking the original upload error.
        try:
            await storage.delete(settings.BUCKET_VOICE_CONSENT, audio_key)
        except Exception:
            log.exception("voice_clone_orphan_cleanup_failed", audio_key=audio_key)
        raise

    req = VoiceCloneRequest(
        id=request_id,
        org_id=token.org_id,
        created_by_id=token.user_id,
        name=name,
        audio_sample_key=audio_key,
        audio_sample_file_name=file.filename or "",
        audio_sample_content_type=file.content_type or "audio/mpeg",
        consent_video_key=video_key,
        consent_video_file_name=consent_video.filename or "",
        consent_video_content_type=consent_video.content_type or "video/webm",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return _request_out(req)


@router.delete("/{item_id}", status_code=204)
async def delete_cloned_voice(
    item_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cloned = await db.get(ClonedVoice, item_id)
    if cloned and cloned.org_id == token.org_id and not cloned.deleted_at:
        cloned.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        async with aiohttp.ClientSession() as http:
            await delete_voice(http, api_key=settings.ELEVENLABS_API_KEY, voice_id=cloned.elevenlabs_voice_id)
        return

    # Not a ClonedVoice — allow withdrawing a still-pending request, or
    # dismissing a rejected one, from the same delete button in the UI.
    req = await db.get(VoiceCloneRequest, item_id)
    if not req or req.org_id != token.org_id or req.status not in ("pending", "rejected"):
        raise NotFoundError("Cloned voice not found")

    storage = get_storage()
    await storage.delete(settings.BUCKET_VOICE_CONSENT, req.audio_sample_key)
    await storage.delete(settings.BUCKET_VOICE_CONSENT, req.consent_video_key)
    await db.delete(req)
    await db.commit()
