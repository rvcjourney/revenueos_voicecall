"""
app/api/platform.py — SuperAdmin (platform) API.

Fully separate auth path from org users: platform_admins is its own table,
platform tokens carry scope="platform" and no org_id (app/core/security.py:
create_platform_token), and require_platform_admin is the only dependency
that accepts them — see app/core/deps.py for the mutual rejection between
this and the org-user token path.

Every org record returned here is read explicitly by the SuperAdmin crossing
org boundaries on purpose; none of it goes through org-scoped query helpers.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Date, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import aiohttp
import structlog

from app.config import settings
from app.core.billing import compute_blended_monthly_credits
from app.core.credits import reset_credit_period_if_stale, resolve_org_credits_per_month
from app.core.deps import require_platform_admin
from app.core.elevenlabs_voice import ElevenLabsVoiceError, clone_voice, get_account_usage
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError as AppValidationError,
)
from app.core.plan_features import is_voice_cloning_allowed, is_voice_provider_allowed
from app.core.razorpay_client import RazorpayError, sync_plan_to_razorpay
from app.core.security import create_platform_token, verify_password
from app.database import check_db_health, get_db
from app.storage.backend import get_storage
from app.models.agent import VoiceProvider
from app.models.audit_log import AuditLog
from app.models.call import Call, CallOutcome, CallStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.cloned_voice import ClonedVoice
from app.models.invoice import Invoice
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.platform_cost_settings import PlatformCostSettings
from app.models.subscription import Subscription
from app.models.user import Organization, User
from app.models.voice_clone_request import VoiceCloneRequest
from app.schemas.billing import TaxInvoiceListOut, TaxInvoiceOut
from app.schemas.platform import (
    CreditAdjustRequest,
    CreditAdjustResponse,
    OrgDetailOut,
    OrgListItemOut,
    OrgPatchRequest,
    PlanCreateRequest,
    PlanOut,
    PlanUpdateRequest,
    CostSettingsOut,
    CostSettingsUpdateRequest,
    PlatformAdminOut,
    PlatformHealthOut,
    PlatformLoginRequest,
    PlatformMetricsOut,
    PlatformTokenResponse,
    UsageAnalyticsOut,
    VoiceCloneRequestOut,
    VoiceCloneRequestRejectRequest,
)

log = structlog.get_logger(__name__)

router = APIRouter()


def _to_plan_out(p: Plan) -> PlanOut:
    return PlanOut(
        id=str(p.id),
        name=p.name,
        price_minor=p.price_minor,
        currency=p.currency,
        monthly_call_quota=p.monthly_call_quota,
        max_concurrent_calls=p.max_concurrent_calls,
        credits_per_month=p.credits_per_month,
        credit_price_cents=p.credit_price_cents,
        features=p.features,
        is_active=p.is_active,
        discount_price_minor=p.discount_price_minor,
        is_custom_pricing=p.is_custom_pricing,
        is_highlighted=p.is_highlighted,
        marketing_bullets=p.marketing_bullets,
    )


def _plan_price_signature(plan: Plan) -> tuple[int, str]:
    effective = plan.discount_price_minor if plan.discount_price_minor is not None else plan.price_minor
    return (effective, plan.currency)


async def _sync_razorpay_plan_best_effort(plan: Plan) -> None:
    """
    Fully automated Razorpay Plan sync, mirroring this project's established
    "superadmin never touches the provider's own console" philosophy (same
    as the Vobiz/LiveKit inbound-calling automation). Best-effort: a Razorpay
    failure (e.g. keys not configured yet) must never block saving the plan
    itself -- billing/checkout also calls sync_plan_to_razorpay lazily, so an
    unsynced plan self-heals on first real checkout attempt.
    """
    if plan.is_custom_pricing:
        return
    try:
        plan.razorpay_plan_id = await sync_plan_to_razorpay(plan)
    except RazorpayError as exc:
        log.warning("razorpay_plan_sync_failed", plan_id=str(plan.id), error=str(exc))


async def _get_or_create_cost_settings(db: AsyncSession) -> PlatformCostSettings:
    settings_row = await db.get(PlatformCostSettings, 1)
    if settings_row is None:
        settings_row = PlatformCostSettings(id=1)
        db.add(settings_row)
        await db.flush()
    return settings_row


async def _active_subscription(db: AsyncSession, org_id: UUID) -> Subscription | None:
    return await db.scalar(
        select(Subscription).where(
            Subscription.org_id == org_id,
            Subscription.deleted_at.is_(None),
        )
    )


async def _to_org_detail_out(db: AsyncSession, org: Organization) -> OrgDetailOut:
    users_count = await db.scalar(
        select(func.count(User.id)).where(User.org_id == org.id, User.deleted_at.is_(None))
    )
    sub = await _active_subscription(db, org.id)
    plan_name = None
    plan_price_minor = None
    plan_discount_price_minor = None
    plan_currency = None
    if sub:
        plan = await db.get(Plan, sub.plan_id)
        if plan:
            plan_name = plan.name
            plan_price_minor = plan.price_minor
            plan_discount_price_minor = plan.discount_price_minor
            plan_currency = plan.currency

    await reset_credit_period_if_stale(db, org)
    credits_per_month = await resolve_org_credits_per_month(db, org.id)

    return OrgDetailOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        is_active=org.is_active,
        plan_name=plan_name,
        calls_used_this_period=org.calls_used_this_period,
        monthly_call_quota=org.monthly_call_quota,
        created_at=org.created_at.isoformat(),
        users_count=users_count or 0,
        subscription_status=sub.status if sub else None,
        subscription_current_period_end=(
            sub.current_period_end.isoformat() if sub and sub.current_period_end else None
        ),
        credits_used_this_period=org.credits_used_this_period,
        credits_per_month=credits_per_month,
        elevenlabs_enabled=org.elevenlabs_enabled,
        plan_price_minor=plan_price_minor,
        plan_discount_price_minor=plan_discount_price_minor,
        plan_currency=plan_currency,
    )


@router.post("/login", response_model=PlatformTokenResponse)
async def login(body: PlatformLoginRequest, db: AsyncSession = Depends(get_db)):
    admin = await db.scalar(select(PlatformAdmin).where(PlatformAdmin.email == body.email))
    if not admin or not verify_password(body.password, admin.hashed_password):
        raise AuthenticationError("Invalid email or password")
    if not admin.is_active:
        raise AuthenticationError("Account is inactive")

    admin.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return PlatformTokenResponse(
        access_token=create_platform_token(str(admin.id)),
        admin=PlatformAdminOut(id=str(admin.id), email=admin.email, full_name=admin.full_name),
    )


@router.get("/orgs", response_model=list[OrgListItemOut])
async def list_orgs(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """List/search organizations across the whole platform (paginated)."""
    query = select(Organization).where(Organization.deleted_at.is_(None))
    if q:
        query = query.where(
            Organization.name.ilike(f"%{q}%") | Organization.slug.ilike(f"%{q}%")
        )
    orgs = (await db.execute(
        query.order_by(Organization.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()

    result = []
    for org in orgs:
        sub = await _active_subscription(db, org.id)
        plan_name = None
        if sub:
            plan = await db.get(Plan, sub.plan_id)
            plan_name = plan.name if plan else None

        # Live usage: calls_used_this_period/monthly_call_quota are never
        # incremented (see OrgListItemOut's docstring) -- credits_used_this_period
        # is the field campaign workers actually update on every completed call.
        await reset_credit_period_if_stale(db, org)
        credits_per_month = await resolve_org_credits_per_month(db, org.id)

        result.append(OrgListItemOut(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            is_active=org.is_active,
            plan_name=plan_name,
            calls_used_this_period=org.calls_used_this_period,
            monthly_call_quota=org.monthly_call_quota,
            credits_used_this_period=org.credits_used_this_period,
            credits_per_month=credits_per_month,
            created_at=org.created_at.isoformat(),
        ))
    return result


@router.get("/orgs/{org_id}", response_model=OrgDetailOut)
async def get_org(
    org_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")
    return await _to_org_detail_out(db, org)


@router.get("/orgs/{org_id}/invoices", response_model=TaxInvoiceListOut)
async def get_org_invoices(
    org_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    QuickHowl's own generated GST tax invoices for one org (app/core/invoicing.py) --
    same records shown to the org itself on its Billing page (GET /api/billing/tax-invoices),
    surfaced here so SuperAdmin can see a client's payment history without impersonating them.
    """
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")

    result = await db.execute(
        select(Invoice).where(Invoice.org_id == org_id).order_by(Invoice.issued_at.desc())
    )
    rows = result.scalars().all()
    return TaxInvoiceListOut(
        invoices=[
            TaxInvoiceOut(
                id=str(inv.id),
                invoice_number=inv.invoice_number,
                plan_name=inv.plan_name,
                total_minor=inv.total_minor,
                currency=inv.currency,
                issued_at=inv.issued_at.isoformat(),
            )
            for inv in rows
        ]
    )


@router.get("/orgs/{org_id}/invoices/{invoice_id}/pdf")
async def download_org_invoice(
    org_id: UUID,
    invoice_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.org_id != org_id:
        raise NotFoundError("Invoice not found")

    data = await get_storage().download(settings.BUCKET_INVOICES, invoice.storage_key)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )


@router.patch("/orgs/{org_id}", response_model=OrgDetailOut)
async def update_org(
    org_id: UUID,
    body: OrgPatchRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Suspend/activate an org, change its plan, or adjust its monthly call quota."""
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")

    changes: dict = {}

    if body.is_active is not None and body.is_active != org.is_active:
        changes["is_active"] = {"from": org.is_active, "to": body.is_active}
        org.is_active = body.is_active

    if body.monthly_call_quota is not None and body.monthly_call_quota != org.monthly_call_quota:
        changes["monthly_call_quota"] = {
            "from": org.monthly_call_quota,
            "to": body.monthly_call_quota,
        }
        org.monthly_call_quota = body.monthly_call_quota

    if body.elevenlabs_enabled is not None and body.elevenlabs_enabled != org.elevenlabs_enabled:
        changes["elevenlabs_enabled"] = {
            "from": org.elevenlabs_enabled,
            "to": body.elevenlabs_enabled,
        }
        org.elevenlabs_enabled = body.elevenlabs_enabled

    if body.plan_id is not None:
        try:
            plan_uuid = UUID(body.plan_id)
        except ValueError:
            raise AppValidationError("Invalid plan_id", errors=[])
        new_plan = await db.get(Plan, plan_uuid)
        if not new_plan:
            raise AppValidationError("Plan not found", errors=[])

        sub = await _active_subscription(db, org.id)
        if sub:
            # Plan change mid-period: blend old/new credits_per_month for the
            # remainder of the current period (see app/core/billing.py). A fresh
            # period (next reset) runs at the new plan's rate in full.
            await reset_credit_period_if_stale(db, org)
            old_plan = await db.get(Plan, sub.plan_id)
            old_credits = old_plan.credits_per_month if old_plan else new_plan.credits_per_month
            blended = compute_blended_monthly_credits(
                old_plan_credits=old_credits,
                new_plan_credits=new_plan.credits_per_month,
                period_start=org.last_credit_reset_at,
                now=datetime.now(timezone.utc),
            )
            sub.prorated_credits_override = blended
            changes["plan_id"] = {"from": str(sub.plan_id), "to": str(new_plan.id)}
            changes["prorated_credits_this_period"] = blended
            sub.plan_id = new_plan.id
        else:
            db.add(Subscription(org_id=org.id, plan_id=new_plan.id, status="active"))
            changes["plan_id"] = {"from": None, "to": str(new_plan.id)}

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=org.id,
        action="org.update",
        target_type="organization",
        target_id=org.id,
        audit_metadata=changes,
    ))

    await db.commit()
    await db.refresh(org)
    return await _to_org_detail_out(db, org)


@router.delete("/orgs/{org_id}", status_code=204)
async def delete_org(
    org_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete an organization (sets deleted_at, same SoftDeleteMixin
    convention every other table in this codebase uses -- see
    app/models/base.py: "Soft-deleted (never hard-deleted) for compliance
    and audit trail"). Immediately drops the org out of every listing here
    (list_orgs/get_org both filter on deleted_at.is_(None)) -- its rows and
    call history are kept, not erased.

    Refuses to delete an org that has an active (non-deleted) Subscription --
    this is meant for cleaning up abandoned/test orgs that were never on a
    plan, not for offboarding a paying customer (cancel their subscription
    first, or use suspend for a reversible block).
    """
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")

    sub = await _active_subscription(db, org.id)
    if sub is not None:
        raise ConflictError(
            "This organization has an active subscription — cancel it before deleting, "
            "or suspend the org instead."
        )

    org.deleted_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=org.id,
        action="org.delete",
        target_type="organization",
        target_id=org.id,
        audit_metadata={"name": org.name, "slug": org.slug},
    ))

    await db.commit()


@router.post("/orgs/{org_id}/credits/adjust", response_model=CreditAdjustResponse)
async def adjust_org_credits(
    org_id: UUID,
    body: CreditAdjustRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually adjust an org's credit usage counter.
    delta > 0 consumes credits (reduces headroom) — e.g. a manual correction
    for calls billed outside the normal flow.
    delta < 0 grants credits (reduces credits_used_this_period) — e.g. a
    goodwill credit or bonus allotment. Result is clamped at a minimum of 0.
    """
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")

    await reset_credit_period_if_stale(db, org)
    before = org.credits_used_this_period
    org.credits_used_this_period = max(0, before + body.delta)

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=org.id,
        action="credits.adjust",
        target_type="organization",
        target_id=org.id,
        audit_metadata={
            "delta": body.delta,
            "reason": body.reason,
            "from": before,
            "to": org.credits_used_this_period,
        },
    ))

    await db.commit()
    await db.refresh(org)
    credits_per_month = await resolve_org_credits_per_month(db, org.id)
    return CreditAdjustResponse(
        org_id=str(org.id),
        credits_used_this_period=org.credits_used_this_period,
        credits_per_month=credits_per_month,
    )


@router.post("/orgs/{org_id}/credits/reset", response_model=CreditAdjustResponse)
async def reset_org_credits(
    org_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Zero out an org's credit usage counter and start a fresh billing period now."""
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")

    before = org.credits_used_this_period
    org.credits_used_this_period = 0
    org.last_credit_reset_at = datetime.now(timezone.utc)

    sub = await _active_subscription(db, org.id)
    if sub is not None:
        sub.prorated_credits_override = None

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=org.id,
        action="credits.reset",
        target_type="organization",
        target_id=org.id,
        audit_metadata={"from": before, "to": 0},
    ))

    await db.commit()
    await db.refresh(org)
    credits_per_month = await resolve_org_credits_per_month(db, org.id)
    return CreditAdjustResponse(
        org_id=str(org.id),
        credits_used_this_period=org.credits_used_this_period,
        credits_per_month=credits_per_month,
    )


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    plans = (await db.execute(select(Plan).order_by(Plan.price_minor))).scalars().all()
    return [_to_plan_out(p) for p in plans]


@router.post("/plans", response_model=PlanOut, status_code=201)
async def create_plan(
    body: PlanCreateRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    plan = Plan(
        name=body.name,
        price_minor=body.price_minor,
        currency=body.currency,
        monthly_call_quota=body.monthly_call_quota,
        max_concurrent_calls=body.max_concurrent_calls,
        credits_per_month=body.credits_per_month,
        credit_price_cents=body.credit_price_cents,
        features=body.features,
        is_active=body.is_active,
        discount_price_minor=body.discount_price_minor,
        is_custom_pricing=body.is_custom_pricing,
        is_highlighted=body.is_highlighted,
        marketing_bullets=body.marketing_bullets,
    )
    db.add(plan)
    await db.flush()  # assign plan.id before the audit log row references it

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=None,
        action="plan.create",
        target_type="plan",
        target_id=plan.id,
    ))
    await _sync_razorpay_plan_best_effort(plan)
    await db.commit()
    await db.refresh(plan)
    return _to_plan_out(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: UUID,
    body: PlanUpdateRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise NotFoundError("Plan not found")

    old_signature = _plan_price_signature(plan)

    if body.name is not None:
        plan.name = body.name
    if body.price_minor is not None:
        plan.price_minor = body.price_minor
    if body.currency is not None:
        plan.currency = body.currency
    if body.monthly_call_quota is not None:
        plan.monthly_call_quota = body.monthly_call_quota
    if body.max_concurrent_calls is not None:
        plan.max_concurrent_calls = body.max_concurrent_calls
    if body.credits_per_month is not None:
        plan.credits_per_month = body.credits_per_month
    if body.credit_price_cents is not None:
        plan.credit_price_cents = body.credit_price_cents
    if body.features is not None:
        plan.features = body.features
    if body.is_active is not None:
        plan.is_active = body.is_active
    # discount_price_minor is nullable and must be independently clearable
    # (send {"discount_price_minor": null} to remove a discount), so this one
    # field is checked via model_fields_set rather than `is not None` --
    # otherwise there'd be no way to distinguish "clear the discount" from
    # "field omitted, leave unchanged."
    if "discount_price_minor" in body.model_fields_set:
        plan.discount_price_minor = body.discount_price_minor
    if body.is_custom_pricing is not None:
        plan.is_custom_pricing = body.is_custom_pricing
    if body.is_highlighted is not None:
        plan.is_highlighted = body.is_highlighted
    if body.marketing_bullets is not None:
        plan.marketing_bullets = body.marketing_bullets

    # Razorpay Plans are immutable -- a price/currency change (or switching to
    # custom pricing) invalidates the mirrored id so the next sync creates a
    # fresh Razorpay Plan rather than silently keeping the old rate.
    if plan.is_custom_pricing or _plan_price_signature(plan) != old_signature:
        plan.razorpay_plan_id = None

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=None,
        action="plan.update",
        target_type="plan",
        target_id=plan.id,
    ))
    await _sync_razorpay_plan_best_effort(plan)

    await db.commit()
    await db.refresh(plan)
    return _to_plan_out(plan)


# ── Cost settings (for estimated gross margin) ────────────────────────────────

@router.get("/settings/cost", response_model=CostSettingsOut)
async def get_cost_settings(
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    settings_row = await _get_or_create_cost_settings(db)
    await db.commit()
    return CostSettingsOut(cost_per_minute_minor=settings_row.cost_per_minute_minor, currency=settings_row.currency)


@router.patch("/settings/cost", response_model=CostSettingsOut)
async def update_cost_settings(
    body: CostSettingsUpdateRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    settings_row = await _get_or_create_cost_settings(db)
    settings_row.cost_per_minute_minor = body.cost_per_minute_minor

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=None,
        action="cost_settings.update",
        target_type="platform_cost_settings",
        target_id=None,
    ))

    await db.commit()
    await db.refresh(settings_row)
    return CostSettingsOut(cost_per_minute_minor=settings_row.cost_per_minute_minor, currency=settings_row.currency)


@router.get("/metrics", response_model=PlatformMetricsOut)
async def get_metrics(
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide totals, computed directly from the DB — no placeholders."""
    org_count = await db.scalar(
        select(func.count(Organization.id)).where(Organization.deleted_at.is_(None))
    )
    active_campaigns = await db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.status == CampaignStatus.RUNNING,
            Campaign.deleted_at.is_(None),
        )
    )
    # Organization.calls_used_this_period is a legacy counter that's never
    # incremented anywhere (see OrgListItemOut) -- summing it always returns 0.
    # A direct count of Call rows is the real, live cross-tenant total.
    total_calls_used = await db.scalar(select(func.count(Call.id)))
    return PlatformMetricsOut(
        org_count=org_count or 0,
        active_campaigns=active_campaigns or 0,
        total_calls_used=total_calls_used or 0,
    )


# ── Usage analytics ───────────────────────────────────────────────────────────
# Daily calls/credits come straight from the calls table (real, not sampled).
# mrr_minor is a live snapshot (sum of active subscriptions' plan price) --
# there's no subscription-history/payment-ledger table, so a genuine
# revenue-over-time trend isn't derivable without fabricating numbers.

async def _daily_usage_series(db: AsyncSession, *, org_id: UUID | None, days: int = 30) -> list[dict]:
    # func.timezone("UTC", ...) forces the DATE cast to use UTC calendar days
    # regardless of the DB session's timezone setting (this deployment's
    # Postgres session defaults to Asia/Calcutta) -- without it, a bare
    # cast(created_at, Date) buckets by the session's local date, which drifts
    # from the UTC "today" used below to build the day range for ~5.5 hours
    # every day and silently drops that window's calls from the series.
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    filters = [Call.created_at >= window_start]
    if org_id is not None:
        filters.append(Call.org_id == org_id)

    # Built once and reused by reference in SELECT/GROUP BY/ORDER BY -- Postgres
    # requires the GROUP BY expression to match the SELECT expression exactly,
    # and three separately-constructed func.timezone(...) calls each get their
    # own bound parameter, which Postgres doesn't recognize as equivalent.
    day_expr = cast(func.timezone("UTC", Call.created_at), Date)

    rows = (await db.execute(
        select(
            day_expr.label("day"),
            func.count(Call.id).label("calls"),
            func.coalesce(
                func.sum(func.ceil(Call.duration_seconds / 60.0)).filter(Call.status == CallStatus.COMPLETED),
                0,
            ).label("credits"),
        )
        .where(*filters)
        .group_by(day_expr)
        .order_by(day_expr)
    )).all()

    daily_map = {str(r.day): {"calls": r.calls, "credits": int(r.credits)} for r in rows}
    series = []
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        entry = daily_map.get(str(d), {"calls": 0, "credits": 0})
        series.append({"day": d.strftime("%b %d"), "calls": entry["calls"], "credits": entry["credits"]})
    return series


_EFFECTIVE_PRICE = func.coalesce(Plan.discount_price_minor, Plan.price_minor)


async def _current_mrr_minor(db: AsyncSession, *, org_id: UUID | None = None) -> int:
    # Uses the effective (discounted, if set) price -- MRR should reflect what
    # orgs are actually being charged, not each plan's undiscounted list price.
    query = (
        select(func.coalesce(func.sum(_EFFECTIVE_PRICE), 0))
        .select_from(Subscription)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == "active", Subscription.deleted_at.is_(None))
    )
    if org_id is not None:
        query = query.where(Subscription.org_id == org_id)
    return (await db.scalar(query)) or 0


async def _average_effective_price_minor(db: AsyncSession, *, org_id: UUID | None = None) -> int:
    query = (
        select(func.coalesce(func.avg(_EFFECTIVE_PRICE), 0))
        .select_from(Subscription)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(Subscription.status == "active", Subscription.deleted_at.is_(None))
    )
    if org_id is not None:
        query = query.where(Subscription.org_id == org_id)
    return int((await db.scalar(query)) or 0)


async def _usage_analytics_out(db: AsyncSession, *, org_id: UUID | None) -> UsageAnalyticsOut:
    series = await _daily_usage_series(db, org_id=org_id)
    mrr = await _current_mrr_minor(db, org_id=org_id)
    avg_price = await _average_effective_price_minor(db, org_id=org_id)
    cost_settings = await _get_or_create_cost_settings(db)
    await db.commit()

    total_minutes = sum(point["credits"] for point in series)
    cogs = total_minutes * cost_settings.cost_per_minute_minor
    margin = mrr - cogs
    margin_pct = (margin / mrr * 100) if mrr else 0.0

    return UsageAnalyticsOut(
        series=series,
        mrr_minor=mrr,
        average_plan_price_minor=avg_price,
        cost_per_minute_minor=cost_settings.cost_per_minute_minor,
        estimated_cogs_minor_30d=cogs,
        estimated_gross_margin_minor=margin,
        estimated_margin_percent=round(margin_pct, 2),
    )


@router.get("/analytics/usage", response_model=UsageAnalyticsOut)
async def platform_usage_analytics(
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide calls/credits per day (last 30 days) + current MRR + estimated margin."""
    return await _usage_analytics_out(db, org_id=None)


@router.get("/orgs/{org_id}/analytics/usage", response_model=UsageAnalyticsOut)
async def platform_org_usage_analytics(
    org_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Same as /analytics/usage, scoped to a single org — for the org detail page."""
    org = await db.get(Organization, org_id)
    if not org or org.deleted_at:
        raise NotFoundError("Organization not found")
    return await _usage_analytics_out(db, org_id=org_id)


# ── Infrastructure health ─────────────────────────────────────────────────────

# Supabase's Free-tier database size cap (see Dashboard → Usage). Not fetched
# from an API -- there isn't a cheap one for this -- just the known published
# limit, used here purely to render a progress bar. Update if the project is
# ever upgraded off the Free plan.
SUPABASE_FREE_DB_SIZE_LIMIT_BYTES = 500 * 1024 * 1024


async def _db_stats(db: AsyncSession) -> dict:
    """
    Cheap pg_catalog queries only -- no Supabase Management API involved, so
    this works with nothing beyond the DB credentials the app already has.
    Mirrors the checks Supabase's own "Advisor" flags (RLS-disabled public
    tables), plus size/connection numbers for a rough capacity gauge.
    """
    size_bytes = await db.scalar(text("select pg_database_size(current_database())"))
    connections_current = await db.scalar(text("select count(*) from pg_stat_activity"))
    max_connections_raw = await db.scalar(text("show max_connections"))
    tables_missing_rls = (await db.execute(text(
        "select relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r' and relrowsecurity = false "
        "order by relname"
    ))).scalars().all()
    return {
        "size_bytes": int(size_bytes or 0),
        "connections_current": int(connections_current or 0),
        "connections_max": int(max_connections_raw or 0),
        "tables_missing_rls": list(tables_missing_rls),
    }


_GROQ_HEALTH_CACHE_TTL = timedelta(minutes=5)
_groq_health_cache: dict = {"checked_at": None, "ok": None, "error": None}


async def _check_groq_model() -> tuple[bool, str | None]:
    """
    Verifies settings.GROQ_SUMMARY_MODEL (the post-call classification model --
    must match agent/agent.py's GROQ_CLASSIFY_MODEL env var) still exists and
    is reachable on Groq. Groq deprecates models with little to no warning --
    this already broke every call's outcome classification once (Aug 2026)
    before anyone noticed. Cached for 5 minutes so the SuperAdmin dashboard's
    30s health poll doesn't hit Groq's API purely from a browser tab being
    left open.
    """
    now = datetime.now(timezone.utc)
    cached_at = _groq_health_cache["checked_at"]
    if cached_at is not None and now - cached_at < _GROQ_HEALTH_CACHE_TTL:
        return _groq_health_cache["ok"], _groq_health_cache["error"]

    ok, error = False, None
    if not settings.GROQ_API_KEY:
        error = "GROQ_API_KEY not configured"
    else:
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    f"https://api.groq.com/openai/v1/models/{settings.GROQ_SUMMARY_MODEL}",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status == 200:
                        ok = True
                    else:
                        body = await resp.text()
                        error = f"Groq {resp.status}: {body[:300]}"
        except Exception as exc:
            error = str(exc)

    _groq_health_cache.update(checked_at=now, ok=ok, error=error)
    return ok, error


@router.get("/health", response_model=PlatformHealthOut)
async def platform_health(
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Live status of the services this request depends on. `api=True` is
    trivial (this response only exists because the API process is up), but
    included so the frontend can render one uniform status row per service.

    Celery Beat (the scheduler) isn't included -- it doesn't respond to
    inspect/ping the way worker processes do, and it writes its schedule
    state to a volume that isn't mounted into the api container, so there's
    no way to probe it from here without a fragile workaround.
    """
    db_ok = await check_db_health()

    redis_ok = False
    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    def _ping_workers() -> dict:
        from app.workers.celery_app import celery_app

        try:
            return celery_app.control.inspect(timeout=3).ping() or {}
        except Exception:
            return {}

    worker_replies = await asyncio.to_thread(_ping_workers)
    db_stats = await _db_stats(db)

    elevenlabs_usage: dict | None = None
    if settings.ELEVENLABS_API_KEY:
        try:
            async with aiohttp.ClientSession() as http:
                elevenlabs_usage = await get_account_usage(http, api_key=settings.ELEVENLABS_API_KEY)
        except ElevenLabsVoiceError as exc:
            log.warning("platform_health_elevenlabs_check_failed", error=str(exc))

    groq_ok, groq_error = await _check_groq_model()

    from app.workers.tasks.campaign import _STALE_PENDING_AGE  # lazy: see _ping_workers above

    stale_cutoff = datetime.now(timezone.utc) - _STALE_PENDING_AGE
    stale_pending_calls_count = await db.scalar(
        select(func.count(Call.id)).where(
            Call.status == CallStatus.COMPLETED,
            Call.outcome == CallOutcome.PENDING,
            Call.ended_at.is_not(None),
            Call.ended_at <= stale_cutoff,
        )
    ) or 0
    stale_initiated_calls_count = await db.scalar(
        select(func.count(Call.id)).where(
            Call.status == CallStatus.INITIATED,
            Call.ended_at.is_(None),
            Call.started_at <= stale_cutoff,
        )
    ) or 0

    return PlatformHealthOut(
        api=True,
        database=db_ok,
        redis=redis_ok,
        celery_workers_online=len(worker_replies),
        celery_worker_names=list(worker_replies.keys()),
        elevenlabs_ok=elevenlabs_usage is not None,
        elevenlabs_tier=elevenlabs_usage["tier"] if elevenlabs_usage else None,
        elevenlabs_characters_used=elevenlabs_usage["character_count"] if elevenlabs_usage else None,
        elevenlabs_characters_limit=elevenlabs_usage["character_limit"] if elevenlabs_usage else None,
        elevenlabs_next_reset_unix=elevenlabs_usage["next_reset_unix"] if elevenlabs_usage else None,
        db_size_bytes=db_stats["size_bytes"],
        db_size_limit_bytes=SUPABASE_FREE_DB_SIZE_LIMIT_BYTES,
        db_connections_current=db_stats["connections_current"],
        db_connections_max=db_stats["connections_max"],
        db_tables_missing_rls=db_stats["tables_missing_rls"],
        groq_ok=groq_ok,
        groq_error=groq_error,
        stale_pending_calls_count=stale_pending_calls_count,
        stale_initiated_calls_count=stale_initiated_calls_count,
    )


# ── Voice clone request review ───────────────────────────────────────────────
# Consent gate in front of ClonedVoice creation (app/api/voice_cloning.py):
# an org admin submits a name + audio sample + consent video, which sits here
# as "pending" until reviewed. Approving is what actually calls ElevenLabs and
# creates the real ClonedVoice row; rejecting just records a reason the org
# admin can see. See app/models/voice_clone_request.py for the full design note.

async def _to_voice_clone_request_out(db: AsyncSession, req: VoiceCloneRequest) -> VoiceCloneRequestOut:
    org = await db.get(Organization, req.org_id)
    user = await db.get(User, req.created_by_id) if req.created_by_id else None
    # Not a presigned MinIO URL: MinIO is internal-only (see docker-compose.yml),
    # so a browser can never reach `http://minio:9000` directly. These paths are
    # this router's own proxy endpoints below, authenticated the same way as
    # every other platform-admin request.
    audio_url = f"/api/platform/voice-clone-requests/{req.id}/audio"
    video_url = f"/api/platform/voice-clone-requests/{req.id}/video"

    return VoiceCloneRequestOut(
        id=str(req.id),
        org_id=str(req.org_id),
        org_name=org.name if org else "Unknown org",
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        name=req.name,
        audio_url=audio_url,
        video_url=video_url,
        status=req.status,
        rejection_reason=req.rejection_reason,
        reviewed_at=req.reviewed_at.isoformat() if req.reviewed_at else None,
        created_at=req.created_at.isoformat(),
    )


@router.get("/voice-clone-requests", response_model=list[VoiceCloneRequestOut])
async def list_voice_clone_requests(
    status: str = Query("pending"),
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(VoiceCloneRequest)
    if status != "all":
        query = query.where(VoiceCloneRequest.status == status)
    if q:
        query = query.join(Organization, Organization.id == VoiceCloneRequest.org_id).where(
            Organization.name.ilike(f"%{q}%") | VoiceCloneRequest.name.ilike(f"%{q}%")
        )
    rows = (await db.execute(
        query.order_by(VoiceCloneRequest.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return [await _to_voice_clone_request_out(db, r) for r in rows]


@router.get("/voice-clone-requests/{request_id}/audio")
async def get_voice_clone_request_audio(
    request_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(VoiceCloneRequest, request_id)
    if not req:
        raise NotFoundError("Voice clone request not found")
    data = await get_storage().download(settings.BUCKET_VOICE_CONSENT, req.audio_sample_key)
    return Response(content=data, media_type=req.audio_sample_content_type or "audio/mpeg")


@router.get("/voice-clone-requests/{request_id}/video")
async def get_voice_clone_request_video(
    request_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(VoiceCloneRequest, request_id)
    if not req:
        raise NotFoundError("Voice clone request not found")
    data = await get_storage().download(settings.BUCKET_VOICE_CONSENT, req.consent_video_key)
    return Response(content=data, media_type=req.consent_video_content_type or "video/webm")


@router.post("/voice-clone-requests/{request_id}/approve", response_model=VoiceCloneRequestOut)
async def approve_voice_clone_request(
    request_id: UUID,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(VoiceCloneRequest, request_id)
    if not req:
        raise NotFoundError("Voice clone request not found")
    if req.status != "pending":
        raise ConflictError(f"Request has already been {req.status}")

    # Re-check gates at approval time — the org's plan or the ElevenLabs
    # kill-switch may have changed since submission (could be days earlier).
    if not await is_voice_cloning_allowed(db, req.org_id):
        raise ConflictError("This org's plan no longer allows voice cloning")
    if not await is_voice_provider_allowed(db, req.org_id, VoiceProvider.ELEVENLABS):
        raise ConflictError("Voice cloning has since been disabled for this org")

    sample_bytes = await get_storage().download(settings.BUCKET_VOICE_CONSENT, req.audio_sample_key)

    try:
        async with aiohttp.ClientSession() as http:
            elevenlabs_voice_id = await clone_voice(
                http,
                api_key=settings.ELEVENLABS_API_KEY,
                name=req.name,
                sample_bytes=sample_bytes,
                sample_filename=req.audio_sample_file_name or "sample.mp3",
                content_type=req.audio_sample_content_type,
            )
    except ElevenLabsVoiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cloned = ClonedVoice(
        org_id=req.org_id,
        created_by_id=req.created_by_id,
        name=req.name,
        elevenlabs_voice_id=elevenlabs_voice_id,
        sample_file_name=req.audio_sample_file_name,
    )
    db.add(cloned)
    await db.flush()  # assign cloned.id before the request references it

    req.status = "approved"
    req.reviewed_by_admin_id = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    req.cloned_voice_id = cloned.id

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=req.org_id,
        action="voice_clone_request.approve",
        target_type="voice_clone_request",
        target_id=req.id,
        audit_metadata={"cloned_voice_id": str(cloned.id), "elevenlabs_voice_id": elevenlabs_voice_id},
    ))

    await db.commit()
    await db.refresh(req)
    return await _to_voice_clone_request_out(db, req)


@router.post("/voice-clone-requests/{request_id}/reject", response_model=VoiceCloneRequestOut)
async def reject_voice_clone_request(
    request_id: UUID,
    body: VoiceCloneRequestRejectRequest,
    admin: PlatformAdmin = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(VoiceCloneRequest, request_id)
    if not req:
        raise NotFoundError("Voice clone request not found")
    if req.status != "pending":
        raise ConflictError(f"Request has already been {req.status}")
    if not body.reason.strip():
        raise AppValidationError("A rejection reason is required", errors=[])

    req.status = "rejected"
    req.rejection_reason = body.reason.strip()
    req.reviewed_by_admin_id = admin.id
    req.reviewed_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=req.org_id,
        action="voice_clone_request.reject",
        target_type="voice_clone_request",
        target_id=req.id,
        audit_metadata={"reason": req.rejection_reason},
    ))

    await db.commit()
    await db.refresh(req)
    return await _to_voice_clone_request_out(db, req)
