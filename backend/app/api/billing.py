"""
app/api/billing.py — Tenant-facing billing endpoints.

GET /current exposes the org's real, superadmin-controlled plan/subscription.
POST /checkout, /verify-payment, /cancel wire in real Razorpay Subscriptions
billing — see app/core/razorpay_client.py for the confirmed Razorpay API/SDK
contract this is built against.

Activation/suspension is never decided here -- POST /verify-payment only
confirms the Checkout handler's signature for immediate UI feedback. The
Razorpay webhook (app/api/webhooks.py: POST /razorpay) is the sole source of
truth for actually flipping org.is_active / Subscription.status, since only
the webhook is a genuine server-to-server call Razorpay signs independently
(a malicious frontend could otherwise fake a "payment succeeded" call here).
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.core.razorpay_client import (
    RazorpayError,
    cancel_subscription as razorpay_cancel_subscription,
    create_subscription as razorpay_create_subscription,
    sync_plan_to_razorpay,
    update_subscription_plan as razorpay_update_subscription_plan,
    verify_subscription_payment_signature,
)
from app.config import settings
from app.database import get_db
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization
from app.schemas.billing import (
    CancelSubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from app.schemas.platform import BillingCurrentOut, PublicPlanOut

log = structlog.get_logger(__name__)

router = APIRouter()

_ACTIVE_RAZORPAY_STATUSES = ("created", "authenticated", "active", "pending")


async def _active_subscription(db: AsyncSession, org_id) -> Subscription | None:
    return await db.scalar(
        select(Subscription).where(Subscription.org_id == org_id, Subscription.deleted_at.is_(None))
    )


@router.get("/current", response_model=BillingCurrentOut)
async def get_current_billing(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await _active_subscription(db, token.org_id)
    if not sub:
        raise NotFoundError("No active subscription for this organization")

    plan = await db.get(Plan, sub.plan_id)
    if not plan:
        raise NotFoundError("Plan not found")

    org = await db.get(Organization, token.org_id)

    return BillingCurrentOut(
        plan=PublicPlanOut(
            id=str(plan.id),
            name=plan.name,
            price_minor=plan.price_minor,
            discount_price_minor=plan.discount_price_minor,
            currency=plan.currency,
            credits_per_month=plan.credits_per_month,
            is_custom_pricing=plan.is_custom_pricing,
            is_highlighted=plan.is_highlighted,
            marketing_bullets=plan.marketing_bullets,
        ),
        subscription_status=sub.status,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        org_active=org.is_active if org else False,
    )


@router.post("/checkout", response_model=CheckoutResponse, status_code=201)
async def checkout(
    body: CheckoutRequest,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(Plan, body.plan_id)
    if not plan or not plan.is_active:
        raise NotFoundError("Plan not found")
    if plan.is_custom_pricing:
        raise ConflictError("This plan has custom pricing — contact sales instead of checking out")

    try:
        razorpay_plan_id = await sync_plan_to_razorpay(plan)
        if not plan.razorpay_plan_id:
            plan.razorpay_plan_id = razorpay_plan_id
            await db.commit()
    except RazorpayError as exc:
        raise ConflictError(str(exc))

    effective_price = plan.discount_price_minor if plan.discount_price_minor is not None else plan.price_minor
    sub = await _active_subscription(db, token.org_id)

    try:
        if sub and sub.provider == "razorpay" and sub.status in _ACTIVE_RAZORPAY_STATUSES:
            # Already has a mandate authorized — change the plan in place,
            # no new Checkout/authorization needed.
            await razorpay_update_subscription_plan(sub.provider_subscription_id, razorpay_plan_id)
            sub.plan_id = plan.id
            await db.commit()
            return CheckoutResponse(
                action="change",
                plan_name=plan.name,
                amount_minor=effective_price,
                currency=plan.currency,
            )

        # First-time (or non-Razorpay) subscription: create a fresh Razorpay
        # Subscription and open Checkout to authorize the recurring mandate.
        razorpay_sub = await razorpay_create_subscription(razorpay_plan_id=razorpay_plan_id, org_id=str(token.org_id))
    except RazorpayError as exc:
        raise ConflictError(str(exc))

    if sub:
        sub.plan_id = plan.id
        sub.provider = "razorpay"
        sub.provider_subscription_id = razorpay_sub["id"]
        sub.status = razorpay_sub["status"]
    else:
        sub = Subscription(
            org_id=token.org_id,
            plan_id=plan.id,
            status=razorpay_sub["status"],
            provider="razorpay",
            provider_subscription_id=razorpay_sub["id"],
        )
        db.add(sub)
    await db.commit()

    return CheckoutResponse(
        action="new",
        subscription_id=razorpay_sub["id"],
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
        plan_name=plan.name,
        amount_minor=effective_price,
        currency=plan.currency,
    )


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    body: VerifyPaymentRequest,
    token: TokenPayload = Depends(require_admin),
):
    """
    Confirms the Checkout handler's signature for immediate UI feedback only.
    Does NOT activate the org or subscription -- the webhook does that.
    """
    try:
        verify_subscription_payment_signature(
            razorpay_subscription_id=body.razorpay_subscription_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_signature=body.razorpay_signature,
        )
    except RazorpayError:
        log.warning("razorpay_payment_signature_invalid", org_id=str(token.org_id))
        return VerifyPaymentResponse(verified=False)
    return VerifyPaymentResponse(verified=True)


@router.post("/cancel", response_model=CancelSubscriptionResponse)
async def cancel(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    sub = await _active_subscription(db, token.org_id)
    if not sub or sub.provider != "razorpay" or not sub.provider_subscription_id:
        raise NotFoundError("No Razorpay subscription to cancel")

    try:
        result = await razorpay_cancel_subscription(sub.provider_subscription_id)
    except RazorpayError as exc:
        raise ConflictError(str(exc))

    sub.status = result["status"]
    await db.commit()
    return CancelSubscriptionResponse(status=sub.status)
