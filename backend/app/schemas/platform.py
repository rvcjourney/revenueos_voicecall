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
    features: dict = {}
    is_active: bool = True


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    price_minor: int | None = None
    currency: str | None = None
    monthly_call_quota: int | None = None
    max_concurrent_calls: int | None = None
    features: dict | None = None
    is_active: bool | None = None


class PlanOut(BaseModel):
    id: str
    name: str
    price_minor: int
    currency: str
    monthly_call_quota: int
    max_concurrent_calls: int
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


class OrgPatchRequest(BaseModel):
    is_active: bool | None = None
    plan_id: str | None = None
    monthly_call_quota: int | None = None


class PlatformMetricsOut(BaseModel):
    org_count: int
    active_campaigns: int
    total_calls_used: int
