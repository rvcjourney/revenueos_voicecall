"""
tests/test_demo_call.py — Free "Try Now" demo call (app/api/agents.py:
try_now, app/workers/tasks/campaign.py:place_demo_call/_run_demo_call_async).

LiveKit (_place_call/_wait_for_room_empty) is always mocked -- these tests
never touch the network. The one behavior that must never regress: a demo
call never calls record_call_credits, however it ends.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import app.workers.tasks.campaign as campaign_module
from app.core.security import create_access_token
from app.models.call import Call, CallDirection, CallStatus
from app.models.user import Organization, User, UserRole


async def _make_admin(db) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
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


async def test_try_now_places_call_on_default_trunk(client, db, fake_redis):
    org, user, token = await _make_admin(db)

    with (
        patch.object(campaign_module, "_place_call", new_callable=AsyncMock, return_value="placed") as mock_place,
        patch.object(campaign_module, "_wait_for_room_empty", new_callable=AsyncMock, return_value="done"),
        patch.object(campaign_module, "record_call_credits", new_callable=AsyncMock) as mock_credits,
        patch.object(campaign_module, "resolve_vobiz_credentials", new_callable=AsyncMock, return_value=None),
        patch.object(campaign_module.settings, "DEFAULT_SIP_TRUNK_ID", "ST_default_demo"),
        patch.object(campaign_module.settings, "DEFAULT_SIP_CALLER_ID", "+910000000000"),
        # The endpoint itself only enqueues onto Celery -- never actually run
        # here, since there's no real broker in tests. _run_demo_call_async is
        # called directly below to simulate "the worker picked it up."
        patch.object(campaign_module.place_demo_call, "apply_async", MagicMock()),
    ):
        resp = await client.post(
            "/api/agents/try-now",
            json={"phone_number": "9876543210"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        call_id = resp.json()["call_id"]

        # apply_async in the real endpoint enqueues on Celery -- run the same
        # underlying coroutine directly here, same as how the task would.
        call_row = await db.get(Call, uuid.UUID(call_id))
        await campaign_module._run_demo_call_async(
            "+919876543210", call_id, str(org.id), str(user.id)
        )

    mock_place.assert_awaited_once()
    kwargs = mock_place.call_args.kwargs
    assert kwargs["livekit_trunk_id"] == "ST_default_demo"
    assert kwargs["sip_caller_id"] == "+910000000000"
    assert kwargs["system_prompt"]  # the fixed demo persona, not empty
    assert kwargs["llm_model"] == "llama-3.3-70b-versatile"

    # The one invariant that must never regress: never charged.
    mock_credits.assert_not_called()

    await db.refresh(call_row)
    assert call_row.status == CallStatus.COMPLETED
    assert call_row.org_id == org.id


async def test_try_now_no_answer_does_not_charge_credits(db, fake_redis):
    org, user, token = await _make_admin(db)
    call = Call(
        org_id=org.id,
        phone_number="+919876543210",
        direction=CallDirection.OUTBOUND,
        status=CallStatus.INITIATED,
        livekit_room_name=f"demo-{uuid.uuid4().hex}",
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    with (
        patch.object(campaign_module, "_place_call", new_callable=AsyncMock, return_value="no_answer"),
        patch.object(campaign_module, "record_call_credits", new_callable=AsyncMock) as mock_credits,
        patch.object(campaign_module.settings, "DEFAULT_SIP_TRUNK_ID", "ST_default_demo"),
        patch.object(campaign_module.settings, "DEFAULT_SIP_CALLER_ID", "+910000000000"),
    ):
        await campaign_module._run_demo_call_async("+919876543210", str(call.id), str(org.id), str(user.id))

    mock_credits.assert_not_called()
    await db.refresh(call)
    assert call.status == CallStatus.NO_ANSWER


async def test_try_now_requires_admin(client, db):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    member = User(
        org_id=org.id,
        email=f"member-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Member",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    token = create_access_token(str(member.id), str(org.id), member.role)

    resp = await client.post(
        "/api/agents/try-now",
        json={"phone_number": "9876543210"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_try_now_respects_user_concurrency_slot(client, db, fake_redis):
    org, user, token = await _make_admin(db)

    from app.core.concurrency import acquire_user_slot

    assert await acquire_user_slot(user.id) is True  # simulate a call already in flight

    resp = await client.post(
        "/api/agents/try-now",
        json={"phone_number": "9876543210"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
