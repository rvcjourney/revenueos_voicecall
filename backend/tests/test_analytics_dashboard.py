"""
tests/test_analytics_dashboard.py — GET /api/analytics/dashboard (app/api/analytics.py).

Regression coverage: the Dashboard header's "Total calls (all time)" /
"Interested leads" used to come from GET /api/admin/stats, which sums
Campaign.completed_calls/interested_count across non-deleted users' campaigns
only -- silently missing inbound calls, Try Now/demo calls, and campaigns
whose creator was later removed. That made it disagree with Call History's
real COUNT(*) over the calls table. total_calls/total_interested here are
computed the same way Call History's totals are (a real, unrestricted count),
so they should agree.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token, hash_password
from app.models.call import Call, CallOutcome
from app.models.user import Organization, User, UserRole


async def _make_org_and_admin(db) -> tuple[Organization, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, token


def _make_call(org_id, campaign_id=None, *, outcome: CallOutcome) -> Call:
    return Call(
        org_id=org_id,
        campaign_id=campaign_id,
        livekit_room_name=f"room-{uuid.uuid4().hex}",
        phone_number="+919876543210",
        outcome=outcome,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )


async def test_dashboard_total_calls_counts_every_call_including_inbound(client, db):
    """No campaign_id (e.g. inbound/demo calls) must still count -- this is
    exactly the category GET /api/admin/stats's campaign-sum approach missed."""
    org, token = await _make_org_and_admin(db)

    for _ in range(3):
        db.add(_make_call(org.id, campaign_id=None, outcome=CallOutcome.INTERESTED))
    for _ in range(2):
        db.add(_make_call(org.id, campaign_id=None, outcome=CallOutcome.NOT_INTERESTED))
    await db.commit()

    resp = await client.get("/api/analytics/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 5
    assert body["total_interested"] == 3


async def test_dashboard_totals_scoped_to_org(client, db):
    org_a, token_a = await _make_org_and_admin(db)
    org_b, _token_b = await _make_org_and_admin(db)

    db.add(_make_call(org_a.id, outcome=CallOutcome.INTERESTED))
    for _ in range(4):
        db.add(_make_call(org_b.id, outcome=CallOutcome.INTERESTED))
    await db.commit()

    resp = await client.get("/api/analytics/dashboard", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    assert resp.json()["total_calls"] == 1
