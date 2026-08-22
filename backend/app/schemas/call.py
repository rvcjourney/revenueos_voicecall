from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    speaker: str
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


class CallOut(BaseModel):
    id: str
    campaign_id: str | None
    phone_number: str
    direction: str
    status: str
    outcome: str
    sentiment: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    cost_inr: float | None
    summary: str | None
    recording_url: str | None
    created_at: datetime


class CallDetail(CallOut):
    extracted_data: dict
    error_message: str | None
    transcript_segments: list[TranscriptSegment]
    transcript_full_text: str | None


class CallListResponse(BaseModel):
    items: list[CallOut]
    total: int
    # Aggregates over the full filtered result set (org_id + campaign_id/outcome
    # filters), not just the returned page -- `items` is capped at `limit`
    # (max 200), so summary stats must come from here, not len(items)/items.
    interested_count: int
    avg_duration_seconds: int
