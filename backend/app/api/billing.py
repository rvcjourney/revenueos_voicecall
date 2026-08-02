"""
app/api/billing.py — Tenant-facing billing endpoints.

GET /current exposes the org's real, superadmin-controlled plan/subscription
so the Billing page can stop showing hardcoded placeholder data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.schemas.platform import BillingCurrentOut, PublicPlanOut

router = APIRouter()


@router.get("/current", response_model=BillingCurrentOut)
async def get_current_billing(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.scalar(
        select(Subscription).where(
            Subscription.org_id == token.org_id,
            Subscription.deleted_at.is_(None),
        )
    )
    if not sub:
        raise NotFoundError("No active subscription for this organization")

    plan = await db.get(Plan, sub.plan_id)
    if not plan:
        raise NotFoundError("Plan not found")

    return BillingCurrentOut(
        plan=PublicPlanOut(
            id=str(plan.id),
            name=plan.name,
            price_minor=plan.price_minor,
            discount_price_minor=plan.discount_price_minor,
            currency=plan.currency,
            credits_per_month=plan.credits_per_month,
            is_custom_pricing=plan.is_custom_pricing,
            is_highlighted=plan.is_highlighted,
            marketing_bullets=plan.marketing_bullets,
        ),
        subscription_status=sub.status,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
    )
