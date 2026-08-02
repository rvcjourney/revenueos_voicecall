"""
app/api/plans.py — Public plan catalog.

Unauthenticated on purpose: the marketing site's pricing section fetches this
before a visitor has logged in. Only display-safe fields are exposed (see
PublicPlanOut in app/schemas/platform.py) -- no internal plan-gating
`features` dict, no inactive plans.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.plan import Plan
from app.schemas.platform import PublicPlanOut

router = APIRouter()


def _to_public_plan_out(p: Plan) -> PublicPlanOut:
    return PublicPlanOut(
        id=str(p.id),
        name=p.name,
        price_minor=p.price_minor,
        discount_price_minor=p.discount_price_minor,
        currency=p.currency,
        credits_per_month=p.credits_per_month,
        is_custom_pricing=p.is_custom_pricing,
        is_highlighted=p.is_highlighted,
        marketing_bullets=p.marketing_bullets,
    )


@router.get("", response_model=list[PublicPlanOut])
async def list_public_plans(db: AsyncSession = Depends(get_db)):
    plans = (
        await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_minor))
    ).scalars().all()
    return [_to_public_plan_out(p) for p in plans]
