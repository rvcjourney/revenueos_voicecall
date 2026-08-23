"""
tests/test_agent_test_call.py — POST /api/agents/{id}/test-call
(app/api/agents.py:test_call).

Covers the two gates added to close blockers 4 and 5 of the 2026-08-23
readiness audit: a 3/hour-per-org rate limit (this is meant to stay usable
by every org regardless of plan/payment status -- NOT a paywall gate) and a
DNC check, mirroring the free "Try Now" demo call's existing behavior
(test_demo_call.py).

LiveKit/Celery dispatch (place_test_call.apply_async) is always mocked --
these tests never touch the network.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.security import create_access_token
from app.models.call import Call
from app.models.dnc import DNCReason, DoNotCallEntry
from app.models.user import Organization, User, UserRole


async def _make_admin(db, *, org_is_active: bool = True) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=org_is_active)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id,
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(str(user.id), str(org.id), user.role)
    return org, user, token


async def _make_agent(db, org: Organization):
    from app.models.agent import AgentTemplate

    agent = AgentTemplate(org_id=org.id, name="Sales Bot")
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


def _place_test_call_mock():
    return patch("app.workers.tasks.campaign.place_test_call.apply_async", MagicMock())


async def test_test_call_blocked_by_dnc(client, db, fake_redis):
    org, _user, token = await _make_admin(db)
    agent = await _make_agent(db, org)
    db.add(DoNotCallEntry(org_id=org.id, phone_number="+919876543210", reason=DNCReason.MANUAL_BLOCK))
    await db.commit()

    with _place_test_call_mock() as mock_dispatch:
        resp = await client.post(
            f"/api/agents/{agent.id}/test-call",
            json={"phone_number": "+919876543210"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422
    assert "Do Not Call" in resp.json()["detail"]
    mock_dispatch.assert_not_called()


async def test_test_call_succeeds_under_the_hourly_limit(client, db, fake_redis):
    org, _user, token = await _make_admin(db)
    agent = await _make_agent(db, org)

    with _place_test_call_mock() as mock_dispatch:
        resp = await client.post(
            f"/api/agents/{agent.id}/test-call",
            json={"phone_number": "+919876543210"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    call_id = resp.json()["call_id"]
    mock_dispatch.assert_called_once()

    call = await db.get(Call, uuid.UUID(call_id))
    assert call is not None
    assert call.org_id == org.id


async def test_test_call_rejects_a_fourth_call_within_the_hour(client, db, fake_redis):
    from app.core.concurrency import release_user_slot

    org, user, token = await _make_admin(db)
    agent = await _make_agent(db, org)
    headers = {"Authorization": f"Bearer {token}"}

    with _place_test_call_mock():
        for i in range(3):
            resp = await client.post(
                f"/api/agents/{agent.id}/test-call",
                json={"phone_number": f"+9198765432{i:02d}"},
                headers=headers,
            )
            assert resp.status_code == 202, resp.text
            # apply_async is mocked -- the real worker (which releases this
            # user's 1-call slot when the call ends) never runs, so release it
            # manually to isolate this test to the rate limit, not the
            # separate single-call-in-flight cap.
            await release_user_slot(user.id)

        fourth = await client.post(
            f"/api/agents/{agent.id}/test-call",
            json={"phone_number": "+919876543299"},
            headers=headers,
        )

    assert fourth.status_code == 429
    body = fourth.json()
    assert body["code"] == "RATE_LIMITED"
    assert "3 per hour" in body["detail"]
    assert "minute" in body["detail"]
    assert body["retry_after_seconds"] > 0
    assert fourth.headers["Retry-After"] == str(body["retry_after_seconds"])


async def test_test_call_rate_limit_is_per_org_not_global(client, db, fake_redis):
    from app.core.concurrency import release_user_slot

    org_a, user_a, token_a = await _make_admin(db)
    agent_a = await _make_agent(db, org_a)
    org_b, _user_b, token_b = await _make_admin(db)
    agent_b = await _make_agent(db, org_b)

    with _place_test_call_mock():
        for i in range(3):
            resp = await client.post(
                f"/api/agents/{agent_a.id}/test-call",
                json={"phone_number": f"+9198765432{i:02d}"},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert resp.status_code == 202
            await release_user_slot(user_a.id)

        # org_a is now at its limit -- org_b must be unaffected.
        resp_b = await client.post(
            f"/api/agents/{agent_b.id}/test-call",
            json={"phone_number": "+919876543210"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
    assert resp_b.status_code == 202


async def test_test_call_allowed_for_org_with_no_active_subscription(client, db, fake_redis):
    """Explicit product decision (2026-08-23): test calls stay usable by every
    org for evaluation purposes, including orgs with no purchased plan at all
    -- NOT gated on org.is_active. Regression guard against that gate being
    reintroduced by mistake."""
    org, _user, token = await _make_admin(db, org_is_active=False)
    agent = await _make_agent(db, org)

    with _place_test_call_mock() as mock_dispatch:
        resp = await client.post(
            f"/api/agents/{agent.id}/test-call",
            json={"phone_number": "+919876543210"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    mock_dispatch.assert_called_once()
