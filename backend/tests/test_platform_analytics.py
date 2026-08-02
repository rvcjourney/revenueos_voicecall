"""
tests/test_platform_analytics.py — Platform usage analytics + infra health.

/api/platform/analytics/usage and /api/platform/orgs/{id}/analytics/usage
derive their numbers straight from the calls table (no fabricated trend
data); /api/platform/health reports live service status.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.core.elevenlabs_voice import ElevenLabsVoiceError
from app.core.security import create_platform_token, hash_password
from app.models.call import Call, CallDirection, CallStatus
from app.models.platform_admin import PlatformAdmin
from app.models.user import Organization


async def _make_platform_admin(db) -> tuple[PlatformAdmin, str]:
    admin = PlatformAdmin(
        email=f"super-{uuid.uuid4().hex[:8]}@motmvoice.test",
        hashed_password=hash_password("super-pw-123"),
        full_name="Super Admin",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin, create_platform_token(str(admin.id))


async def _make_org(db, name: str) -> Organization:
    org = Organization(name=name, slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


def _make_call(org_id, *, duration_seconds: int, status=CallStatus.COMPLETED) -> Call:
    return Call(
        org_id=org_id,
        livekit_room_name=f"room-{uuid.uuid4().hex}",
        phone_number="+919876543210",
        direction=CallDirection.OUTBOUND,
        status=status,
        started_at=datetime.now(timezone.utc),
        duration_seconds=duration_seconds,
    )


async def test_platform_health_returns_live_status(client, db):
    _admin, token = await _make_platform_admin(db)

    with patch(
        "app.api.platform.get_account_usage",
        new=AsyncMock(return_value={
            "tier": "creator",
            "character_count": 12_000,
            "character_limit": 100_000,
            "next_reset_unix": 1_800_000_000,
            "status": "active",
        }),
    ):
        resp = await client.get("/api/platform/health", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()

    # api is trivially True (this response only exists because the process is
    # up) -- database should be reachable too, since tests run against a real
    # Postgres. redis/celery are genuinely environment-dependent (no broker
    # running in the test environment), so only assert their shape, not value.
    assert body["api"] is True
    assert body["database"] is True
    assert isinstance(body["redis"], bool)
    assert isinstance(body["celery_workers_online"], int)
    assert isinstance(body["celery_worker_names"], list)

    assert body["elevenlabs_ok"] is True
    assert body["elevenlabs_tier"] == "creator"
    assert body["elevenlabs_characters_used"] == 12_000
    assert body["elevenlabs_characters_limit"] == 100_000


async def test_platform_health_elevenlabs_failure_degrades_gracefully(client, db):
    _admin, token = await _make_platform_admin(db)

    with patch(
        "app.api.platform.get_account_usage",
        new=AsyncMock(side_effect=ElevenLabsVoiceError("Invalid ElevenLabs API key")),
    ):
        resp = await client.get("/api/platform/health", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["elevenlabs_ok"] is False
    assert body["elevenlabs_characters_used"] is None


async def test_platform_usage_analytics_counts_real_calls(client, db):
    _admin, token = await _make_platform_admin(db)
    org = await _make_org(db, "Acme Inc")

    # 5-minute completed call -> 5 credits; a no_answer call contributes 0
    # credits regardless of duration (only connected calls bill call-minutes).
    db.add(_make_call(org.id, duration_seconds=300))
    db.add(_make_call(org.id, duration_seconds=999, status=CallStatus.NO_ANSWER))
    await db.commit()

    resp = await client.get("/api/platform/analytics/usage", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["series"]) == 30
    today = body["series"][-1]
    assert today["calls"] == 2
    assert today["credits"] == 5
    assert isinstance(body["mrr_minor"], int)


async def test_platform_org_usage_analytics_scoped_to_one_org(client, db):
    _admin, token = await _make_platform_admin(db)
    org_a = await _make_org(db, "Org A")
    org_b = await _make_org(db, "Org B")

    db.add(_make_call(org_a.id, duration_seconds=120))
    db.add(_make_call(org_b.id, duration_seconds=600))
    db.add(_make_call(org_b.id, duration_seconds=600))
    await db.commit()

    resp = await client.get(
        f"/api/platform/orgs/{org_a.id}/analytics/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    today = resp.json()["series"][-1]
    assert today["calls"] == 1
    assert today["credits"] == 2


async def test_platform_org_usage_analytics_404_for_unknown_org(client, db):
    _admin, token = await _make_platform_admin(db)

    resp = await client.get(
        f"/api/platform/orgs/{uuid.uuid4()}/analytics/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
