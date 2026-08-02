"""
app/schemas/platform.py — Pydantic schemas for the SuperAdmin (platform) API.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformAdminOut(BaseModel):
    id: str
    email: str
    full_name: str | None


class PlatformTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: PlatformAdminOut


class PlanCreateRequest(BaseModel):
    name: str
    price_minor: int
    currency: str = "INR"
    monthly_call_quota: int
    max_concurrent_calls: int
    credits_per_month: int = 500
    credit_price_cents: int = 10
    features: dict = {}
    is_active: bool = True


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    price_minor: int | None = None
    currency: str | None = None
    monthly_call_quota: int | None = None
    max_concurrent_calls: int | None = None
    credits_per_month: int | None = None
    credit_price_cents: int | None = None
    features: dict | None = None
    is_active: bool | None = None


class PlanOut(BaseModel):
    id: str
    name: str
    price_minor: int
    currency: str
    monthly_call_quota: int
    max_concurrent_calls: int
    credits_per_month: int
    credit_price_cents: int
    features: dict
    is_active: bool


class OrgListItemOut(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    plan_name: str | None
    calls_used_this_period: int
    monthly_call_quota: int
    created_at: str


class OrgDetailOut(OrgListItemOut):
    users_count: int
    subscription_status: str | None
    subscription_current_period_end: str | None
    credits_used_this_period: int
    credits_per_month: int
    elevenlabs_enabled: bool


class OrgPatchRequest(BaseModel):
    is_active: bool | None = None
    plan_id: str | None = None
    monthly_call_quota: int | None = None
    elevenlabs_enabled: bool | None = None


class CreditAdjustRequest(BaseModel):
    # Positive = consume credits (reduces headroom). Negative = grant credits
    # (reduces credits_used_this_period, increasing headroom). Result is
    # clamped at a minimum of 0 — usage can't go negative.
    delta: int
    reason: str


class CreditAdjustResponse(BaseModel):
    org_id: str
    credits_used_this_period: int
    credits_per_month: int


class PlatformMetricsOut(BaseModel):
    org_count: int
    active_campaigns: int
    total_calls_used: int


class VoiceCloneRequestOut(BaseModel):
    id: str
    org_id: str
    org_name: str
    user_name: str | None
    user_email: str | None
    name: str
    audio_url: str
    video_url: str
    status: str  # "pending" | "approved" | "rejected"
    rejection_reason: str | None
    reviewed_at: str | None
    created_at: str


class VoiceCloneRequestRejectRequest(BaseModel):
    reason: str


class UsageSeriesPoint(BaseModel):
    day: str
    calls: int
    credits: int


class UsageAnalyticsOut(BaseModel):
    """
    Real, derived data only: daily calls/credits come straight from the calls
    table, and mrr_minor is the sum of active subscriptions' plan price right
    now. There's no subscription-history/payment-ledger table yet, so a true
    revenue-over-time trend can't be computed without fabricating numbers —
    mrr_minor is a current snapshot, not a series.
    """
    series: list[UsageSeriesPoint]
    mrr_minor: int
    currency: str = "INR"


class PlatformHealthOut(BaseModel):
    api: bool
    database: bool
    redis: bool
    celery_workers_online: int
    celery_worker_names: list[str]
