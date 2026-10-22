"""
tests/test_engine_switches.py — the owner's "Calling engines" switches in /ops:
global kill-switch, per-org flags, per-language grid, audit log, the <=60 s
cache, paused campaigns, and the per-engine cost rate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core import pipelines as p
from app.models.audit_log import AuditLog
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignStatus
from tests.test_premium_features import _make_org_and_admin, _make_platform_admin


async def _owner(db):
    _, token = await _make_platform_admin(db)
    p.invalidate_owner_settings()
    return {"Authorization": f"Bearer {token}"}


async def test_global_switch_stops_new_sarvam_calls_and_is_audited(client, db):
    org, _, _ = await _make_org_and_admin(db)
    org.sarvam_pipeline_enabled = True
    await db.commit()
    h = await _owner(db)

    engine = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline="sarvam", agent_pipeline=None,
                                         language="hindi", voice_id="", voice_provider="sarvam")
    assert engine.pipeline == "sarvam"

    r = await client.patch("/api/platform/engines", json={"global_enabled": False}, headers=h)
    assert r.status_code == 200 and r.json()["global_enabled"] is False
    hindi = next(l for l in r.json()["languages"] if l["key"] == "hindi")
    assert hindi["sarvam"]["effective"] == "off: global switch"

    engine = await p.resolve_call_engine(db, org_id=org.id, campaign_pipeline="sarvam", agent_pipeline=None,
                                         language="hindi", voice_id="", voice_provider="sarvam")
    assert (engine.pipeline, engine.fallback) == ("standard", True)
    log = await db.scalar(select(AuditLog).where(AuditLog.action == "engines.update"))
    assert log.audit_metadata["global_enabled"] == {"from": True, "to": False}


async def test_language_grid_validates_and_records_changes(client, db):
    h = await _owner(db)
    r = await client.patch("/api/platform/engines", json={"languages": {"malayalam": {"sarvam": {"enabled": True}}}}, headers=h)
    assert next(l for l in r.json()["languages"] if l["key"] == "malayalam")["sarvam"]["effective"] == "on"

    r = await client.patch("/api/platform/engines", json={"languages": {"hindi": {"sarvam": {"tts_model": "bulbul:v3"}}}}, headers=h)
    hindi = next(l for l in r.json()["languages"] if l["key"] == "hindi")["sarvam"]
    assert hindi["tts_model"] == "bulbul:v3" and "ritu" in {v["id"] for v in hindi["voices"]}

    bad = await client.patch("/api/platform/engines", json={"languages": {"hindi": {"sarvam": {"voices": ["ritu_hi_conversation"]}}}}, headers=h)
    assert bad.status_code == 422  # a v4-flash name isn't valid once Hindi is on v3
    ok = await client.patch("/api/platform/engines", json={"languages": {"hindi": {"sarvam": {"voices": ["ritu", "shubh"]}}}}, headers=h)
    assert next(l for l in ok.json()["languages"] if l["key"] == "hindi")["sarvam"]["shortlist"] == ["ritu", "shubh"]
    assert {v.id for v in p.sarvam_voices("hindi", await p.get_owner_settings(db))} == {"ritu", "shubh"}

    logs = (await db.execute(select(AuditLog).where(AuditLog.action == "engines.update"))).scalars().all()
    assert len(logs) == 3  # the rejected change wrote nothing


async def test_org_flags_effective_state_and_audit(client, db):
    org, _, _ = await _make_org_and_admin(db)
    h = await _owner(db)
    detail = (await client.get(f"/api/platform/orgs/{org.id}", headers=h)).json()
    assert (detail["sarvam_pipeline_enabled"], detail["sarvam_effective"]) == (False, "off: organisation")
    r = await client.patch(f"/api/platform/orgs/{org.id}", json={"sarvam_pipeline_enabled": True, "default_pipeline": "sarvam",
                                                                 "sarvam_cloning_allowed": True}, headers=h)
    assert r.status_code == 200
    assert (r.json()["sarvam_effective"], r.json()["default_pipeline"]) == ("on", "sarvam")
    log = await db.scalar(select(AuditLog).where(AuditLog.action == "org.update", AuditLog.org_id == org.id))
    assert log.audit_metadata["sarvam_pipeline_enabled"] == {"from": False, "to": True}


async def test_cached_toggle_is_picked_up_within_60_seconds(db, monkeypatch):
    from app.models.platform_cost_settings import PlatformCostSettings
    clock = [1000.0]
    monkeypatch.setattr(p.time, "monotonic", lambda: clock[0])
    p.invalidate_owner_settings()
    row = PlatformCostSettings(id=1)
    db.add(row)
    await db.commit()
    assert (await p.get_owner_settings(db)).global_enabled is True
    row.sarvam_pipeline_global_enabled = False  # e.g. changed by another process
    await db.commit()
    clock[0] += 30
    assert (await p.get_owner_settings(db)).global_enabled is True   # still cached
    clock[0] += 31
    assert (await p.get_owner_settings(db)).global_enabled is False  # <= 60 s later


async def test_paused_campaigns_are_listed(client, db):
    org, user, _ = await _make_org_and_admin(db)
    db.add(Campaign(org_id=org.id, created_by_id=user.id, name="Clone camp", status=CampaignStatus.PAUSED,
                    pause_reason=p.PAUSE_REASON_ENGINE_OFF))
    await db.commit()
    h = await _owner(db)
    paused = (await client.get("/api/platform/engines", headers=h)).json()["paused_campaigns"]
    assert [c["name"] for c in paused] == ["Clone camp"]


async def test_sarvam_minutes_costed_at_their_own_rate(client, db):
    org, _, _ = await _make_org_and_admin(db)
    now = datetime.now(timezone.utc)
    for pipe in ("standard", "sarvam", "sarvam"):
        db.add(Call(org_id=org.id, livekit_room_name=f"r-{uuid.uuid4().hex}", phone_number="+919999999999",
                    direction=CallDirection.OUTBOUND, status=CallStatus.COMPLETED, pipeline=pipe,
                    duration_seconds=120, started_at=now, answered_at=now, ended_at=now))
    await db.commit()
    h = await _owner(db)
    r = await client.patch("/api/platform/settings/cost", json={"cost_per_minute_minor": 100, "sarvam_cost_per_minute_minor": 60}, headers=h)
    assert r.json()["sarvam_cost_per_minute_minor"] == 60
    usage = (await client.get("/api/platform/analytics/usage", headers=h)).json()
    assert usage["minutes_by_pipeline"] == {"standard": 2, "sarvam": 4}
