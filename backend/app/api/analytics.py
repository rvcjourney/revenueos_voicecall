from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import cast, Date, func, select
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
    # Same four counts as before, computed with conditional aggregates so they
    # round-trip to the DB once instead of four times.
    kpi_row = (await db.execute(
        select(
            func.count(Call.id).label("calls_today"),
            func.count(Call.id).filter(Call.outcome == "interested").label("interested_today"),
            func.avg(Call.duration_seconds).filter(Call.duration_seconds.is_not(None)).label("avg_duration"),
            func.count(Call.id).filter(Call.status == "completed").label("answered"),
        ).where(*call_filter, Call.created_at >= today_start)
    )).one()

    calls_today = kpi_row.calls_today
    interested_today = kpi_row.interested_today
    avg_duration = kpi_row.avg_duration
    answered = kpi_row.answered

    pickup_rate = round((answered / calls_today * 100), 1) if calls_today else 0

    # All-time totals for the dashboard header -- a real, unrestricted COUNT
    # over the same call_filter used everywhere else on this page (org-wide
    # for admins, own campaigns only for members). Previously the header
    # sourced these from GET /api/admin/stats, which sums Campaign.completed_calls/
    # interested_count across non-deleted users' campaigns only -- silently
    # excluding inbound calls, Try Now/demo calls, and campaigns whose creator
    # was later removed from the org, so it drifted from Call History's real
    # total (which counts every Call row directly) the more of those an org had.
    all_time_row = (await db.execute(
        select(
            func.count(Call.id).label("total_calls"),
            func.count(Call.id).filter(Call.outcome == "interested").label("total_interested"),
        ).where(*call_filter)
    )).one()

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
        "call_dropped":       "oklch(0.65 0.18 55)",
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
        "total_calls": all_time_row.total_calls,
        "total_interested": all_time_row.total_interested,
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
