"""
tests/test_calls_list.py — GET /api/calls (app/api/calls.py:list_calls).

Regression coverage for a real bug: the frontend's Call History page computed
its "Total calls"/"Interested"/"Avg. duration" stat cards from len()/filter()
over the returned `items` page, which is capped at `limit` (max 200) -- an
org with more calls than that saw wildly undercounted stats that also
disagreed with the Dashboard's real all-time totals. The fix moved these into
real aggregate columns on the response, computed over the whole filtered set
independent of limit/offset.
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


def _make_call(org_id, *, outcome: CallOutcome, duration_seconds: int | None) -> Call:
    return Call(
        org_id=org_id,
        livekit_room_name=f"room-{uuid.uuid4().hex}",
        phone_number="+919876543210",
        outcome=outcome,
        duration_seconds=duration_seconds,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )


async def test_list_calls_totals_reflect_full_set_not_just_the_page(client, db):
    """250 calls exist, but the page is capped at limit=200 -- total/
    interested_count/avg_duration_seconds must still reflect all 250, not
    just the 200 returned in `items`."""
    org, token = await _make_org_and_admin(db)

    for i in range(250):
        outcome = CallOutcome.INTERESTED if i < 30 else CallOutcome.NOT_INTERESTED
        db.add(_make_call(org.id, outcome=outcome, duration_seconds=60))
    # A handful of no-duration (never connected) calls shouldn't drag the average down
    for _ in range(5):
        db.add(_make_call(org.id, outcome=CallOutcome.NO_ANSWER, duration_seconds=None))
    await db.commit()

    resp = await client.get(
        "/api/calls", params={"limit": 200}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["items"]) == 200      # page capped as requested
    assert body["total"] == 255           # but totals cover everything
    assert body["interested_count"] == 30
    assert body["avg_duration_seconds"] == 60


async def test_list_calls_totals_respect_filters(client, db):
    org, token = await _make_org_and_admin(db)

    for _ in range(3):
        db.add(_make_call(org.id, outcome=CallOutcome.INTERESTED, duration_seconds=120))
    for _ in range(4):
        db.add(_make_call(org.id, outcome=CallOutcome.NOT_INTERESTED, duration_seconds=30))
    await db.commit()

    resp = await client.get(
        "/api/calls", params={"outcome": "interested"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["interested_count"] == 3
    assert body["avg_duration_seconds"] == 120


async def test_list_calls_totals_scoped_to_org(client, db):
    org_a, token_a = await _make_org_and_admin(db)
    org_b, _token_b = await _make_org_and_admin(db)

    db.add(_make_call(org_a.id, outcome=CallOutcome.INTERESTED, duration_seconds=60))
    for _ in range(10):
        db.add(_make_call(org_b.id, outcome=CallOutcome.INTERESTED, duration_seconds=60))
    await db.commit()

    resp = await client.get("/api/calls", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
