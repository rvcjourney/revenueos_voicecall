from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user
from app.database import get_db
from app.models.call import Call
from app.models.campaign import Campaign

router = APIRouter()


@router.get("/dashboard")
async def dashboard_stats(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = token.org_id
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)

    # Admins see org-wide stats; members see only their own campaigns' stats
    call_filter = [Call.org_id == org_id]
    if token.role != "admin":
        member_camp_ids = select(Campaign.id).where(
            Campaign.org_id == org_id,
            Campaign.created_by_id == token.user_id,
            Campaign.deleted_at.is_(None),
        )
        call_filter.append(Call.campaign_id.in_(member_camp_ids))

    # ── KPIs ──────────────────────────────────────────────────────────────────
    calls_today = (await db.execute(
        select(func.count(Call.id)).where(*call_filter, Call.created_at >= today_start)
    )).scalar_one()

    interested_today = (await db.execute(
        select(func.count(Call.id)).where(
            *call_filter, Call.created_at >= today_start, Call.outcome == "interested"
        )
    )).scalar_one()

    avg_duration = (await db.execute(
        select(func.avg(Call.duration_seconds)).where(
            *call_filter, Call.created_at >= today_start, Call.duration_seconds.is_not(None)
        )
    )).scalar_one()

    answered = (await db.execute(
        select(func.count(Call.id)).where(
            *call_filter, Call.created_at >= today_start, Call.status == "completed"
        )
    )).scalar_one()

    pickup_rate = round((answered / calls_today * 100), 1) if calls_today else 0

    # ── Calls over last 7 days ─────────────────────────────────────────────────
    daily_rows = (await db.execute(
        select(
            cast(Call.created_at, Date).label("day"),
            func.count(Call.id).label("calls"),
            func.count(Call.id).filter(Call.outcome == "interested").label("interested"),
        )
        .where(*call_filter, Call.created_at >= seven_days_ago)
        .group_by(cast(Call.created_at, Date))
        .order_by(cast(Call.created_at, Date))
    )).all()

    daily_map = {str(r.day): {"calls": r.calls, "interested": r.interested or 0} for r in daily_rows}
    calls_last_7_days = []
    for i in range(6, -1, -1):
        d = (now - timedelta(days=i)).date()
        key = str(d)
        calls_last_7_days.append({
            "day": d.strftime("%a"),
            "calls": daily_map.get(key, {}).get("calls", 0),
            "interested": daily_map.get(key, {}).get("interested", 0),
        })

    # ── Outcome breakdown (last 30 days) ──────────────────────────────────────
    thirty_days_ago = now - timedelta(days=30)
    outcome_rows = (await db.execute(
        select(Call.outcome, func.count(Call.id).label("cnt"))
        .where(*call_filter, Call.created_at >= thirty_days_ago)
        .group_by(Call.outcome)
    )).all()

    outcome_colors = {
        "interested":         "oklch(0.7 0.16 160)",
        "not_interested":     "oklch(0.5 0.03 265)",
        "no_answer":          "oklch(0.4 0.03 265)",
        "callback_requested": "oklch(0.62 0.21 280)",
        "voicemail":          "oklch(0.55 0.12 200)",
        "wrong_number":       "oklch(0.5 0.08 30)",
        "do_not_call":        "oklch(0.45 0.05 265)",
        "pending":            "oklch(0.62 0.23 25)",
    }
    outcome_breakdown = [
        {
            "name": r.outcome.replace("_", " ").title(),
            "value": r.cnt,
            "color": outcome_colors.get(r.outcome, "oklch(0.5 0.05 265)"),
        }
        for r in outcome_rows
    ]

    # ── Active campaigns ───────────────────────────────────────────────────────
    camp_filter = [
        Campaign.org_id == org_id,
        Campaign.status.in_(["running", "scheduled"]),
        Campaign.deleted_at.is_(None),
    ]
    if token.role != "admin":
        camp_filter.append(Campaign.created_by_id == token.user_id)

    active_campaigns = (await db.execute(
        select(Campaign).where(*camp_filter).order_by(Campaign.started_at.desc()).limit(5)
    )).scalars().all()

    return {
        "kpis": {
            "calls_today": calls_today,
            "interested_today": interested_today,
            "avg_duration_seconds": int(avg_duration) if avg_duration else 0,
            "pickup_rate": pickup_rate,
        },
        "calls_last_7_days": calls_last_7_days,
        "outcome_breakdown": outcome_breakdown,
        "active_campaigns": [
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "total_contacts": c.total_contacts,
                "completed_calls": c.completed_calls,
                "interested_count": c.interested_count,
            }
            for c in active_campaigns
        ],
    }
