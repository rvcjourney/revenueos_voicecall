"""
tests/test_pricing_and_margin.py — Public plan catalog (app/api/plans.py),
tenant billing (app/api/billing.py), and SuperAdmin cost settings /
margin analytics (app/api/platform.py: /settings/cost, /analytics/usage
margin fields).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.security import create_access_token, create_platform_token, hash_password
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.subscription import Subscription
from app.models.user import Organization, User, UserRole
from app.models.call import Call, CallDirection, CallStatus


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


async def _make_plan(db, **overrides) -> Plan:
    defaults = dict(
        name=f"Plan-{uuid.uuid4().hex[:6]}",
        price_minor=100_000,
        monthly_call_quota=1000,
        max_concurrent_calls=5,
        credits_per_month=500,
        credit_price_cents=10,
        is_active=True,
    )
    defaults.update(overrides)
    plan = Plan(**defaults)
    db.add(plan)
    await db.flush()
    return plan


async def _make_org_with_subscription(db, plan: Plan) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active"))

    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Acme Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, user, token


# ── Public plan catalog ─────────────────────────────────────────────────────

async def test_public_plans_lists_only_active_ordered_by_price(client, db):
    await _make_plan(db, name="Enterprise", price_minor=2_899_900, is_active=True)
    await _make_plan(db, name="Starter", price_minor=499_900, is_active=True)
    await _make_plan(db, name="Retired", price_minor=1, is_active=False)
    await db.commit()

    resp = await client.get("/api/plans")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == ["Starter", "Enterprise"]


async def test_public_plans_custom_pricing_plan_hides_price_via_flag(client, db):
    await _make_plan(
        db, name="Business", price_minor=999_999_900, is_custom_pricing=True,
        is_highlighted=False, marketing_bullets=["24/7 inbound call handling"],
    )
    await db.commit()

    resp = await client.get("/api/plans")
    assert resp.status_code == 200
    business = next(p for p in resp.json() if p["name"] == "Business")
    assert business["is_custom_pricing"] is True
    assert business["marketing_bullets"] == ["24/7 inbound call handling"]


async def test_public_plans_shows_discount_price_when_set(client, db):
    await _make_plan(db, name="Professional", price_minor=1_499_900, discount_price_minor=999_900)
    await db.commit()

    resp = await client.get("/api/plans")
    plan = next(p for p in resp.json() if p["name"] == "Professional")
    assert plan["price_minor"] == 1_499_900
    assert plan["discount_price_minor"] == 999_900


# ── Tenant billing ───────────────────────────────────────────────────────────

async def test_billing_current_returns_orgs_real_plan(client, db):
    plan = await _make_plan(db, name="Starter", price_minor=499_900, credits_per_month=500)
    _org, _user, token = await _make_org_with_subscription(db, plan)

    resp = await client.get("/api/billing/current", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["name"] == "Starter"
    assert body["plan"]["price_minor"] == 499_900
    assert body["subscription_status"] == "active"


async def test_billing_current_404_without_subscription(client, db):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Acme Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.get("/api/billing/current", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


# ── SuperAdmin cost settings ────────────────────────────────────────────────

async def test_cost_settings_get_defaults_to_zero(client, db):
    _admin, token = await _make_platform_admin(db)

    resp = await client.get("/api/platform/settings/cost", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"cost_per_minute_minor": 0, "currency": "INR"}


async def test_cost_settings_update_persists(client, db):
    _admin, token = await _make_platform_admin(db)

    resp = await client.patch(
        "/api/platform/settings/cost",
        json={"cost_per_minute_minor": 150},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["cost_per_minute_minor"] == 150

    resp2 = await client.get("/api/platform/settings/cost", headers={"Authorization": f"Bearer {token}"})
    assert resp2.json()["cost_per_minute_minor"] == 150


# ── Margin analytics ─────────────────────────────────────────────────────────

async def test_usage_analytics_computes_estimated_margin(client, db):
    _admin, token = await _make_platform_admin(db)
    plan = await _make_plan(db, name="Starter", price_minor=500_000)
    org, _user, _token = await _make_org_with_subscription(db, plan)

    # 10-minute completed call today -> 10 credits (minutes) of COGS exposure.
    db.add(Call(
        org_id=org.id,
        livekit_room_name=f"room-{uuid.uuid4().hex}",
        phone_number="+919876543210",
        direction=CallDirection.OUTBOUND,
        status=CallStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        duration_seconds=600,
    ))
    await db.commit()

    await client.patch(
        "/api/platform/settings/cost",
        json={"cost_per_minute_minor": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get("/api/platform/analytics/usage", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["mrr_minor"] == 500_000
    assert body["average_plan_price_minor"] == 500_000
    assert body["cost_per_minute_minor"] == 1000
    assert body["estimated_cogs_minor_30d"] == 10 * 1000
    assert body["estimated_gross_margin_minor"] == 500_000 - 10 * 1000
    assert body["estimated_margin_percent"] == round((500_000 - 10 * 1000) / 500_000 * 100, 2)


async def test_average_price_uses_discounted_price_when_set(client, db):
    _admin, token = await _make_platform_admin(db)
    plan = await _make_plan(db, name="Professional", price_minor=1_499_900, discount_price_minor=999_900)
    await _make_org_with_subscription(db, plan)

    resp = await client.get("/api/platform/analytics/usage", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["mrr_minor"] == 999_900
    assert body["average_plan_price_minor"] == 999_900


# ── SuperAdmin plan CRUD: new pricing-card fields ───────────────────────────

async def test_create_plan_persists_new_pricing_fields(client, db):
    _admin, token = await _make_platform_admin(db)

    resp = await client.post(
        "/api/platform/plans",
        json={
            "name": "Business",
            "price_minor": 999_999_900,
            "monthly_call_quota": 0,
            "max_concurrent_calls": 50,
            "is_custom_pricing": True,
            "is_highlighted": False,
            "marketing_bullets": ["24/7 inbound call handling", "AI script builder"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_custom_pricing"] is True
    assert body["discount_price_minor"] is None
    assert body["marketing_bullets"] == ["24/7 inbound call handling", "AI script builder"]


async def test_update_plan_can_set_and_clear_discount_price(client, db):
    _admin, token = await _make_platform_admin(db)
    plan = await _make_plan(db, name="Professional", price_minor=1_499_900)
    await db.commit()

    set_resp = await client.patch(
        f"/api/platform/plans/{plan.id}",
        json={"discount_price_minor": 999_900},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["discount_price_minor"] == 999_900

    clear_resp = await client.patch(
        f"/api/platform/plans/{plan.id}",
        json={"discount_price_minor": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["discount_price_minor"] is None

    unrelated_resp = await client.patch(
        f"/api/platform/plans/{plan.id}",
        json={"is_highlighted": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unrelated_resp.status_code == 200
    # discount stayed cleared -- omitting the field must not resurrect it.
    assert unrelated_resp.json()["discount_price_minor"] is None
    assert unrelated_resp.json()["is_highlighted"] is True
