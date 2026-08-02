from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ClonedVoiceOut(BaseModel):
    id: str
    name: str
    elevenlabs_voice_id: str | None = None
    status: str  # "ready" | "failed" | "pending" | "rejected"
    rejection_reason: str | None = None
    created_at: datetime


class ClonedVoiceListResponse(BaseModel):
    items: list[ClonedVoiceOut]
