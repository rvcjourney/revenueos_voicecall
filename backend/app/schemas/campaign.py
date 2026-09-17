from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, field_validator


class FolderOut(BaseModel):
    id: str
    name: str
    color: str | None
    campaign_count: int
    created_at: datetime


class FolderCreate(BaseModel):
    name: str
    color: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class CampaignOut(BaseModel):
    id: str
    name: str
    description: str | None
    notes: str | None = None
    status: str
    goal: str
    folder_id: str | None
    agent_template_id: str
    total_contacts: int
    completed_calls: int
    interested_count: int
    failed_count: int
    calling_window_start: str
    calling_window_end: str
    calling_days: list[str]
    timezone: str
    calls_per_minute: int
    max_retries: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    created_by_name: str | None = None
    is_prime: bool = False


class CampaignListResponse(BaseModel):
    items: list[CampaignOut]
    total: int


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None
    notes: str | None = None
    goal: str = "lead_generation"
    folder_id: UUID | None = None
    agent_template_id: UUID
    sip_trunk_id: UUID | None = None
    calling_window_start: time = time(9, 0, 0)
    calling_window_end: time = time(19, 0, 0)
    calling_days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat"]
    timezone: str = "Asia/Kolkata"
    calls_per_minute: int = 5
    max_retries: int = 2
    retry_after_minutes: int = 60
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_prime: bool = False

    @field_validator("calling_window_start", "calling_window_end", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        if isinstance(v, str):
            return time.fromisoformat(v)
        return v


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None
    status: str | None = None
    calling_window_start: time | None = None
    calling_window_end: time | None = None
    calling_days: list[str] | None = None
    timezone: str | None = None
    calls_per_minute: int | None = None
    max_retries: int | None = None

    @field_validator("calling_window_start", "calling_window_end", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        if isinstance(v, str):
            return time.fromisoformat(v)
        return v
