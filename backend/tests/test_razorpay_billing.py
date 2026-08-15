"""
tests/test_razorpay_billing.py — Razorpay Subscriptions billing
(app/api/billing.py, app/api/webhooks.py: POST /razorpay), reopened
self-serve registration (app/api/auth.py), and org.is_active enforcement
(app/api/campaigns.py). Razorpay's SDK is always mocked -- these tests never
touch the network.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.razorpay_client import RazorpayError
from app.core.security import create_access_token, create_platform_token, hash_password
from app.models.agent import AgentTemplate, VoiceProvider
from app.models.campaign import Campaign
from app.models.plan import Plan
from app.models.platform_admin import PlatformAdmin
from app.models.subscription import Subscription
from app.models.user import Organization, User, UserRole


async def _make_plan(db, **overrides) -> Plan:
    defaults = dict(
        name=f"Plan-{uuid.uuid4().hex[:6]}",
        price_minor=499_900,
        monthly_call_quota=500,
        max_concurrent_calls=3,
        credits_per_month=500,
        is_active=True,
    )
    defaults.update(overrides)
    plan = Plan(**defaults)
    db.add(plan)
    await db.flush()
    return plan


async def _make_org_with_subscription(db, plan: Plan, *, sub_overrides: dict | None = None) -> tuple[Organization, User, str]:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()

    sub_kwargs = dict(org_id=org.id, plan_id=plan.id, status="active")
    if sub_overrides:
        sub_kwargs.update(sub_overrides)
    db.add(Subscription(**sub_kwargs))

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


def _webhook_payload(event: str, subscription_id: str, **entity_overrides) -> dict:
    entity = {"id": subscription_id, "status": "active"}
    entity.update(entity_overrides)
    return {
        "entity": "event",
        "event": event,
        "contains": ["subscription"],
        "payload": {"subscription": {"entity": entity}},
        "created_at": 1700000000,
    }


# ── Checkout ─────────────────────────────────────────────────────────────

async def test_checkout_creates_new_subscription(client, db):
    plan = await _make_plan(db, name="Starter")
    org = Organization(name="New Org", slug=f"org-{uuid.uuid4().hex[:8]}")
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

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_abc123")), \
         patch("app.api.billing.razorpay_create_subscription", new=AsyncMock(
             return_value={"id": "sub_abc123", "status": "created"}
         )) as mock_create:
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "new"
    assert body["subscription_id"] == "sub_abc123"
    assert body["razorpay_key_id"] is not None
    mock_create.assert_awaited_once()

    from sqlalchemy import select as _select
    sub = await db.scalar(_select(Subscription).where(Subscription.org_id == org.id))
    assert sub.provider == "razorpay"
    assert sub.provider_subscription_id == "sub_abc123"
    assert sub.status == "created"


async def test_checkout_existing_active_subscription_changes_plan(client, db):
    old_plan = await _make_plan(db, name="Starter")
    new_plan = await _make_plan(db, name="Professional", price_minor=1_499_900)
    org, _user, token = await _make_org_with_subscription(
        db, old_plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_existing", "status": "active"}
    )

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new123")), \
         patch("app.api.billing.razorpay_update_subscription_plan", new=AsyncMock(
             return_value={"id": "sub_existing", "status": "active"}
         )) as mock_edit:
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(new_plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "change"
    mock_edit.assert_awaited_once_with("sub_existing", "plan_new123")


async def test_checkout_upi_subscription_falls_back_to_new_subscription(client, db):
    """Razorpay rejects in-place plan edits for UPI/eMandate-paid subscriptions
    (card-only) -- checkout should cancel the old one and create a fresh
    subscription requiring a new Checkout authorization, same as a first-time
    subscriber, instead of failing the upgrade outright."""
    old_plan = await _make_plan(db, name="Starter")
    new_plan = await _make_plan(db, name="Professional", price_minor=1_499_900)
    org, _user, token = await _make_org_with_subscription(
        db, old_plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_upi_old", "status": "active"}
    )

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new123")), \
         patch("app.api.billing.razorpay_update_subscription_plan", new=AsyncMock(
             side_effect=RazorpayError("Could not change Razorpay subscription plan: subscriptions cannot be updated when payment mode is upi")
         )), \
         patch("app.api.billing.razorpay_cancel_subscription", new=AsyncMock(
             return_value={"id": "sub_upi_old", "status": "cancelled"}
         )) as mock_cancel, \
         patch("app.api.billing.razorpay_create_subscription", new=AsyncMock(
             return_value={"id": "sub_upi_new", "status": "created"}
         )) as mock_create:
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(new_plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "new"
    assert body["subscription_id"] == "sub_upi_new"
    mock_cancel.assert_awaited_once_with("sub_upi_old")
    mock_create.assert_awaited_once()

    from sqlalchemy import select as _select
    sub = await db.scalar(_select(Subscription).where(Subscription.org_id == org.id))
    assert sub.provider_subscription_id == "sub_upi_new"
    assert sub.status == "created"


async def test_checkout_new_subscription_does_not_change_plan_before_payment(client, db):
    """Regression test: plan_id must NOT change until the Razorpay webhook
    confirms payment -- previously it was written here immediately, so
    cancelling/failing the Checkout modal still left the org on a plan it
    never paid for."""
    old_plan = await _make_plan(db, name="Starter", credits_per_month=500)
    new_plan = await _make_plan(db, name="Professional", credits_per_month=2000, price_minor=1_499_900)
    org, _user, token = await _make_org_with_subscription(
        db, old_plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_old", "status": "active"}
    )

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new123")), \
         patch("app.api.billing.razorpay_update_subscription_plan", new=AsyncMock(
             side_effect=RazorpayError("subscriptions cannot be updated when payment mode is upi")
         )), \
         patch("app.api.billing.razorpay_cancel_subscription", new=AsyncMock(return_value={"status": "cancelled"})), \
         patch("app.api.billing.razorpay_create_subscription", new=AsyncMock(
             return_value={"id": "sub_new", "status": "created"}
         )):
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(new_plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201

    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    assert sub.plan_id == old_plan.id          # unchanged -- payment not confirmed yet
    assert sub.pending_plan_id == new_plan.id  # queued instead

    current = await client.get("/api/billing/current", headers={"Authorization": f"Bearer {token}"})
    assert current.json()["plan"]["name"] == "Starter"  # still shows the paid-for plan


async def test_checkout_in_place_plan_change_blends_credits_immediately(client, db):
    """The in-place update path (existing card mandate, no Checkout modal
    shown) genuinely completes synchronously, so applying it immediately is
    correct -- but it should blend remaining-period credits like the
    superadmin manual plan-change path does, not just switch to the new
    plan's fresh allotment."""
    old_plan = await _make_plan(db, name="Starter", credits_per_month=1000)
    new_plan = await _make_plan(db, name="Professional", credits_per_month=4000, price_minor=1_499_900)
    org, _user, token = await _make_org_with_subscription(
        db, old_plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_existing", "status": "active"}
    )
    from datetime import datetime, timedelta, timezone
    org.last_credit_reset_at = datetime.now(timezone.utc) - timedelta(days=15)  # halfway through the period
    org.credits_used_this_period = 100
    await db.commit()

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new123")), \
         patch("app.api.billing.razorpay_update_subscription_plan", new=AsyncMock(
             return_value={"id": "sub_existing", "status": "active"}
         )):
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(new_plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201

    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    assert sub.plan_id == new_plan.id
    # ~15 days at 1000/mo + ~15 days at 4000/mo, not just a flat 4000
    assert 2000 < sub.prorated_credits_override < 3000


async def test_checkout_falls_back_to_new_subscription_when_razorpay_state_stale(client, db):
    """Live incident: our DB had status='active' (so we tried the in-place
    update), but Razorpay's actual subscription state disagreed -- a
    subscription left over from before a test/live-mode key switch, whose
    webhook update never landed. Should fall back the same way the UPI case
    does, not surface a raw 409 to the customer."""
    old_plan = await _make_plan(db, name="Starter")
    new_plan = await _make_plan(db, name="Professional", price_minor=1_499_900)
    org, _user, token = await _make_org_with_subscription(
        db, old_plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_stale_state", "status": "active"}
    )

    with patch("app.api.billing.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new123")), \
         patch("app.api.billing.razorpay_update_subscription_plan", new=AsyncMock(
             side_effect=RazorpayError("Can't update subscription when subscription is not in Authenticated or Active state")
         )), \
         patch("app.api.billing.razorpay_cancel_subscription", new=AsyncMock(return_value={"status": "cancelled"})), \
         patch("app.api.billing.razorpay_create_subscription", new=AsyncMock(
             return_value={"id": "sub_fresh", "status": "created"}
         )):
        resp = await client.post(
            "/api/billing/checkout",
            json={"plan_id": str(new_plan.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["action"] == "new"
    assert body["subscription_id"] == "sub_fresh"

    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    assert sub.plan_id == old_plan.id  # unchanged -- new payment not confirmed yet
    assert sub.pending_plan_id == new_plan.id


async def test_checkout_rejects_custom_pricing_plan(client, db):
    plan = await _make_plan(db, name="Business", is_custom_pricing=True)
    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"), full_name="Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.post(
        "/api/billing/checkout",
        json={"plan_id": str(plan.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ── Payment verification ────────────────────────────────────────────────────

async def test_verify_payment_returns_verified_true_on_valid_signature(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(db, plan)

    with patch("app.api.billing.verify_subscription_payment_signature", return_value=True):
        resp = await client.post(
            "/api/billing/verify-payment",
            json={
                "razorpay_payment_id": "pay_123",
                "razorpay_subscription_id": "sub_123",
                "razorpay_signature": "deadbeef",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["verified"] is True


async def test_verify_payment_returns_verified_false_on_invalid_signature(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(db, plan)

    with patch(
        "app.api.billing.verify_subscription_payment_signature",
        side_effect=RazorpayError("Invalid payment signature"),
    ):
        resp = await client.post(
            "/api/billing/verify-payment",
            json={
                "razorpay_payment_id": "pay_123",
                "razorpay_subscription_id": "sub_123",
                "razorpay_signature": "bad",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["verified"] is False


# ── Cancel ───────────────────────────────────────────────────────────────

async def test_cancel_subscription(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_cancel_me", "status": "active"}
    )

    with patch("app.api.billing.razorpay_cancel_subscription", new=AsyncMock(
        return_value={"id": "sub_cancel_me", "status": "active"}
    )):
        resp = await client.post("/api/billing/cancel", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ── Invoices ─────────────────────────────────────────────────────────────

async def test_list_invoices_returns_empty_without_razorpay_subscription(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(db, plan)  # no provider set

    resp = await client.get("/api/billing/invoices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["invoices"] == []


async def test_list_invoices_returns_razorpay_invoices(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_inv_test", "status": "active"}
    )

    with patch("app.api.billing.list_subscription_invoices", new=AsyncMock(return_value=[
        {"id": "inv_2", "amount": 149900, "currency": "INR", "status": "paid", "issued_at": 1700100000, "short_url": "https://rzp.io/i/2"},
        {"id": "inv_1", "amount": 149900, "currency": "INR", "status": "paid", "issued_at": 1700000000, "short_url": "https://rzp.io/i/1"},
    ])):
        resp = await client.get("/api/billing/invoices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    invoices = resp.json()["invoices"]
    assert len(invoices) == 2
    assert invoices[0]["id"] == "inv_2"  # newest first
    assert invoices[0]["amount_minor"] == 149900
    assert invoices[0]["hosted_url"] == "https://rzp.io/i/2"


async def test_list_invoices_returns_empty_on_razorpay_error(client, db):
    plan = await _make_plan(db)
    _org, _user, token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_inv_err", "status": "active"}
    )

    with patch("app.api.billing.list_subscription_invoices", new=AsyncMock(side_effect=RazorpayError("boom"))):
        resp = await client.get("/api/billing/invoices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["invoices"] == []


# ── Webhook ──────────────────────────────────────────────────────────────

async def test_webhook_rejects_bad_signature(client, db):
    with patch("app.api.webhooks.verify_webhook_signature", side_effect=RazorpayError("Invalid webhook signature")):
        resp = await client.post(
            "/webhooks/razorpay",
            content=json.dumps({"event": "subscription.charged"}),
            headers={"X-Razorpay-Signature": "bad", "Content-Type": "application/json"},
        )
    assert resp.status_code == 401


async def test_webhook_subscription_authenticated_activates_org(client, db):
    plan = await _make_plan(db)
    org, _user, _token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_auth_me", "status": "created"}
    )
    org.is_active = False
    await db.commit()

    payload = _webhook_payload("subscription.authenticated", "sub_auth_me")

    with patch("app.api.webhooks.verify_webhook_signature", return_value=True):
        resp = await client.post(
            "/webhooks/razorpay",
            content=json.dumps(payload),
            headers={"X-Razorpay-Signature": "valid", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200

    await db.refresh(org)
    assert org.is_active is True

    from sqlalchemy import select as _select
    sub = await db.scalar(_select(Subscription).where(Subscription.org_id == org.id))
    assert sub.status == "authenticated"


async def test_webhook_subscription_charged_activates_org_and_resets_credits(client, db):
    plan = await _make_plan(db, credits_per_month=500)
    org, _user, _token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_charge_me", "status": "created"}
    )
    org.is_active = False
    org.credits_used_this_period = 250
    await db.commit()

    payload = _webhook_payload(
        "subscription.charged", "sub_charge_me",
        current_start=1700000000, current_end=1702592000, customer_id="cust_xyz",
    )

    with patch("app.api.webhooks.verify_webhook_signature", return_value=True):
        resp = await client.post(
            "/webhooks/razorpay",
            content=json.dumps(payload),
            headers={"X-Razorpay-Signature": "valid", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200

    await db.refresh(org)
    assert org.is_active is True
    assert org.credits_used_this_period == 0

    from sqlalchemy import select as _select
    sub = await db.scalar(_select(Subscription).where(Subscription.org_id == org.id))
    assert sub.status == "active"
    assert sub.provider_customer_id == "cust_xyz"
    assert sub.current_period_start is not None
    assert sub.current_period_end is not None


async def test_webhook_promotes_pending_plan_on_authenticated_with_blended_credits(client, db):
    """Once the webhook confirms payment for a plan change queued via
    pending_plan_id, plan_id should move over and credits should blend --
    mirroring test_checkout_in_place_plan_change_blends_credits_immediately
    but for the fresh-subscription/Checkout-modal path."""
    old_plan = await _make_plan(db, name="Starter", credits_per_month=1000)
    new_plan = await _make_plan(db, name="Professional", credits_per_month=4000)
    org, _user, _token = await _make_org_with_subscription(
        db, old_plan,
        sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_pending_promo", "status": "created"},
    )
    from datetime import datetime, timedelta, timezone
    org.is_active = False
    org.last_credit_reset_at = datetime.now(timezone.utc) - timedelta(days=15)
    org.credits_used_this_period = 100
    await db.commit()

    sub = await db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    sub.pending_plan_id = new_plan.id
    await db.commit()

    payload = _webhook_payload("subscription.authenticated", "sub_pending_promo")
    with patch("app.api.webhooks.verify_webhook_signature", return_value=True):
        resp = await client.post(
            "/webhooks/razorpay",
            content=json.dumps(payload),
            headers={"X-Razorpay-Signature": "valid", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200

    await db.refresh(sub)
    assert sub.plan_id == new_plan.id
    assert sub.pending_plan_id is None
    assert 2000 < sub.prorated_credits_override < 3000


async def test_webhook_subscription_halted_suspends_org(client, db):
    plan = await _make_plan(db)
    org, _user, _token = await _make_org_with_subscription(
        db, plan, sub_overrides={"provider": "razorpay", "provider_subscription_id": "sub_halt_me", "status": "active"}
    )
    org.is_active = True
    await db.commit()

    payload = _webhook_payload("subscription.halted", "sub_halt_me")

    with patch("app.api.webhooks.verify_webhook_signature", return_value=True):
        resp = await client.post(
            "/webhooks/razorpay",
            content=json.dumps(payload),
            headers={"X-Razorpay-Signature": "valid", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200

    await db.refresh(org)
    assert org.is_active is False


# ── Reopened registration ────────────────────────────────────────────────

async def test_register_creates_inactive_org(client, db):
    email = f"founder-{uuid.uuid4().hex[:8]}@newcotest.com"
    with patch("app.api.auth.send_otp", new_callable=AsyncMock) as mock_send:
        resp = await client.post(
            "/api/auth/register",
            json={
                "full_name": "New Founder",
                "company_name": f"NewCo {uuid.uuid4().hex[:6]}",
                "email": email,
                "password": "password123",
                "phone": "+919876543210",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["email"] == email
    mock_send.assert_awaited_once_with(email)

    # No session yet -- registration alone doesn't activate the org or log
    # anyone in; that only happens once verify-otp confirms the email.
    user = await db.scalar(select(User).where(User.email == email))
    assert user.email_verified_at is None
    org = await db.get(Organization, user.org_id)
    assert org.is_active is False

    with patch("app.api.auth.verify_otp", new_callable=AsyncMock, return_value=True) as mock_verify:
        resp = await client.post(
            "/api/auth/verify-otp", json={"email": email, "code": "123456"}
        )
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    mock_verify.assert_awaited_once_with(email, "123456")

    await db.refresh(user)
    assert user.email_verified_at is not None


# ── org.is_active enforcement ────────────────────────────────────────────

async def test_launch_campaign_rejected_when_org_inactive(client, db):
    org = Organization(name="Suspended Org", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=False)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("admin-pw-123"), full_name="Admin", role=UserRole.ADMIN, is_active=True,
    )
    db.add(user)
    agent = AgentTemplate(org_id=org.id, created_by_id=user.id, name="Bot", voice_provider=VoiceProvider.SARVAM)
    db.add(agent)
    await db.flush()
    campaign = Campaign(org_id=org.id, agent_template_id=agent.id, name="Test Campaign")
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.post(
        f"/api/campaigns/{campaign.id}/launch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── SuperAdmin plan auto-sync ────────────────────────────────────────────

async def test_create_plan_auto_syncs_razorpay_plan(client, db):
    _admin, token = await _make_platform_admin(db)

    with patch("app.api.platform.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_synced_123")):
        resp = await client.post(
            "/api/platform/plans",
            json={
                "name": "Starter",
                "price_minor": 499_900,
                "monthly_call_quota": 500,
                "max_concurrent_calls": 3,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201

    from sqlalchemy import select as _select
    plan = await db.scalar(_select(Plan).where(Plan.name == "Starter"))
    assert plan.razorpay_plan_id == "plan_synced_123"


async def test_update_plan_price_change_resyncs_razorpay_plan(client, db):
    _admin, token = await _make_platform_admin(db)
    plan = await _make_plan(db, name="Starter", price_minor=499_900, razorpay_plan_id="plan_old_123")
    await db.commit()

    with patch("app.api.platform.sync_plan_to_razorpay", new=AsyncMock(return_value="plan_new_456")) as mock_sync:
        resp = await client.patch(
            f"/api/platform/plans/{plan.id}",
            json={"price_minor": 599_900},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["price_minor"] == 599_900
    mock_sync.assert_awaited_once()

    await db.refresh(plan)
    assert plan.razorpay_plan_id == "plan_new_456"
