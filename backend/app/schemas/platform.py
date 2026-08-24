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
    discount_price_minor: int | None = None
    is_custom_pricing: bool = False
    is_highlighted: bool = False
    marketing_bullets: list[str] = []


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
    discount_price_minor: int | None = None
    is_custom_pricing: bool | None = None
    is_highlighted: bool | None = None
    marketing_bullets: list[str] | None = None


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
    discount_price_minor: int | None
    is_custom_pricing: bool
    is_highlighted: bool
    marketing_bullets: list[str]


class PublicPlanOut(BaseModel):
    """Display-safe subset of PlanOut for unauthenticated/tenant consumers."""
    id: str
    name: str
    price_minor: int
    discount_price_minor: int | None
    currency: str
    credits_per_month: int
    is_custom_pricing: bool
    is_highlighted: bool
    marketing_bullets: list[str]


class BillingCurrentOut(BaseModel):
    plan: PublicPlanOut
    subscription_status: str | None
    current_period_end: str | None
    # The real enforcement flag (Organization.is_active) -- checked at campaign
    # launch/dispatch. Prefer this over guessing from subscription_status,
    # since more than one status value counts as "not suspended" (e.g. a
    # freshly authenticated Razorpay mandate, before activated/charged land).
    org_active: bool


class CostSettingsOut(BaseModel):
    cost_per_minute_minor: int
    currency: str


class CostSettingsUpdateRequest(BaseModel):
    cost_per_minute_minor: int


class OrgListItemOut(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    plan_name: str | None
    # Legacy call-count quota -- superseded by credits_used_this_period/
    # credits_per_month below (1 credit = 1 minute), which is what's actually
    # incremented on every completed call (app/core/credits.py). These two
    # are never incremented anywhere and always read 0; kept only because
    # monthly_call_quota remains an editable per-org override (OrgPatchRequest).
    calls_used_this_period: int
    monthly_call_quota: int
    credits_used_this_period: int
    credits_per_month: int
    created_at: str


class OrgDetailOut(OrgListItemOut):
    users_count: int
    subscription_status: str | None
    subscription_current_period_end: str | None
    elevenlabs_enabled: bool
    # Plan pricing snapshot (from the org's currently-assigned Plan, not
    # frozen at signup) -- lets SuperAdmin see what each client is actually
    # being billed without cross-referencing the Plans screen separately.
    plan_price_minor: int | None = None
    plan_discount_price_minor: int | None = None
    plan_currency: str | None = None


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
    table, and mrr_minor is the sum of active subscriptions' effective
    (discounted, if set) plan price right now. There's no subscription-history/
    payment-ledger table yet, so a true revenue-over-time trend can't be
    computed without fabricating numbers — mrr_minor is a current snapshot,
    not a series.

    estimated_cogs_minor_30d / estimated_gross_margin_minor /
    estimated_margin_percent are ESTIMATES: 30-day real call-minutes (from
    `series`) multiplied by the superadmin-set cost_per_minute_minor rate
    (app/api/platform.py: /settings/cost), compared against the MRR snapshot.
    Not a precise per-org P&L — there's no real per-call provider cost capture
    (Groq/ElevenLabs/Vobiz/LiveKit) anywhere in the system yet.
    """
    series: list[UsageSeriesPoint]
    mrr_minor: int
    currency: str = "INR"
    average_plan_price_minor: int
    cost_per_minute_minor: int
    estimated_cogs_minor_30d: int
    estimated_gross_margin_minor: int
    estimated_margin_percent: float


class PlatformHealthOut(BaseModel):
    api: bool
    database: bool
    redis: bool
    celery_workers_online: int
    celery_worker_names: list[str]
    elevenlabs_ok: bool
    elevenlabs_tier: str | None = None
    elevenlabs_characters_used: int | None = None
    elevenlabs_characters_limit: int | None = None
    elevenlabs_next_reset_unix: int | None = None
    db_size_bytes: int
    db_size_limit_bytes: int
    db_connections_current: int
    db_connections_max: int
    db_tables_missing_rls: list[str]
    # Groq deprecated the post-call classification model with no warning once
    # already (Aug 2026) -- every real call silently landed at outcome=pending
    # until someone noticed on the calls page. This actively verifies the
    # model is still valid on Groq instead of waiting to find out from
    # customer-facing symptoms.
    groq_ok: bool
    groq_error: str | None = None
    # COMPLETED calls still sitting at outcome=pending 10+ minutes after
    # ending -- the visible version of the flag_stale_pending_calls Beat task
    # (app/workers/tasks/campaign.py), which previously only wrote a log line
    # nobody was watching. A nonzero count here means SOMETHING in the
    # post-call classification pipeline is broken right now, whatever the
    # cause -- not just the specific Groq-model failure mode above.
    stale_pending_calls_count: int
