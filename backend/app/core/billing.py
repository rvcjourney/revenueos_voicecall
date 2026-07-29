"""
app/core/billing.py — Plan upgrade/downgrade proration.

No payment provider is integrated yet (Subscription.provider is optional/null —
see app/models/subscription.py), so "proration" here means: when an org changes
plan mid-billing-period, the credit allotment for the REST of the current
period is a time-weighted blend of the old and new plan's credits_per_month,
rather than either the full old or full new amount. The next period (once
app/core/credits.py:reset_credit_period_if_stale fires) uses the new plan's
rate in full.

Used by app/api/platform.py's PATCH /orgs/{id} plan-change path.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.credits import CREDIT_PERIOD_DAYS


def compute_blended_monthly_credits(
    *,
    old_plan_credits: int,
    new_plan_credits: int,
    period_start: datetime,
    now: datetime,
    period_days: int = CREDIT_PERIOD_DAYS,
) -> int:
    """
    Time-weighted blend of old/new plan credit allotments for the remainder of
    the current billing period.

    Example: 10 days into a 30-day period, upgrading from a 500-credit plan to
    a 2000-credit plan gives (10/30)*500 + (20/30)*2000 = ~1500 credits for the
    rest of this period; the next period runs at the full 2000.
    """
    period_end = period_start + timedelta(days=period_days)
    total_seconds = (period_end - period_start).total_seconds() or 1.0

    elapsed_seconds = (now - period_start).total_seconds()
    elapsed_seconds = max(0.0, min(elapsed_seconds, total_seconds))
    remaining_seconds = total_seconds - elapsed_seconds

    elapsed_fraction = elapsed_seconds / total_seconds
    remaining_fraction = remaining_seconds / total_seconds

    blended = old_plan_credits * elapsed_fraction + new_plan_credits * remaining_fraction
    return round(blended)
