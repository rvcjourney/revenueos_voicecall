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

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_platform_admin
from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError as AppValidationError
from app.core.security import create_platform_token, verify_password
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign, CampaignStatus
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.subscription import Subscription
from app.models.user import Organization, User
from app.schemas.platform import (
    OrgDetailOut,
    OrgListItemOut,
    OrgPatchRequest,
    PlanCreateRequest,
    PlanOut,
    PlanUpdateRequest,
    PlatformAdminOut,
    PlatformLoginRequest,
    PlatformMetricsOut,
    PlatformTokenResponse,
)

router = APIRouter()


def _to_plan_out(p: Plan) -> PlanOut:
    return PlanOut(
        id=str(p.id),
        name=p.name,
        price_minor=p.price_minor,
        currency=p.currency,
        monthly_call_quota=p.monthly_call_quota,
        max_concurrent_calls=p.max_concurrent_calls,
        features=p.features,
        is_active=p.is_active,
    )


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
    if sub:
        plan = await db.get(Plan, sub.plan_id)
        plan_name = plan.name if plan else None

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
        result.append(OrgListItemOut(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            is_active=org.is_active,
            plan_name=plan_name,
            calls_used_this_period=org.calls_used_this_period,
            monthly_call_quota=org.monthly_call_quota,
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

    if body.plan_id is not None:
        try:
            plan_uuid = UUID(body.plan_id)
        except ValueError:
            raise AppValidationError("Invalid plan_id", errors=[])
        plan = await db.get(Plan, plan_uuid)
        if not plan:
            raise AppValidationError("Plan not found", errors=[])

        sub = await _active_subscription(db, org.id)
        if sub:
            changes["plan_id"] = {"from": str(sub.plan_id), "to": str(plan.id)}
            sub.plan_id = plan.id
        else:
            db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))
            changes["plan_id"] = {"from": None, "to": str(plan.id)}

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
        features=body.features,
        is_active=body.is_active,
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
    if body.features is not None:
        plan.features = body.features
    if body.is_active is not None:
        plan.is_active = body.is_active

    db.add(AuditLog(
        actor_type="platform_admin",
        actor_id=admin.id,
        org_id=None,
        action="plan.update",
        target_type="plan",
        target_id=plan.id,
    ))

    await db.commit()
    await db.refresh(plan)
    return _to_plan_out(plan)


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
    total_calls_used = await db.scalar(
        select(func.coalesce(func.sum(Organization.calls_used_this_period), 0)).where(
            Organization.deleted_at.is_(None)
        )
    )
    return PlatformMetricsOut(
        org_count=org_count or 0,
        active_campaigns=active_campaigns or 0,
        total_calls_used=total_calls_used or 0,
    )
