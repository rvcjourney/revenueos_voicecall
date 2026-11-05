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

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing import compute_blended_monthly_credits
from app.core.credits import reset_credit_period_if_stale
from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.razorpay_client import (
    RazorpayError,
    cancel_subscription as razorpay_cancel_subscription,
    create_subscription as razorpay_create_subscription,
    list_subscription_invoices,
    sync_plan_to_razorpay,
    update_subscription_plan as razorpay_update_subscription_plan,
    verify_subscription_payment_signature,
)
from app.config import settings
from app.database import get_db
from app.models.invoice import Invoice
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization
from app.storage.backend import get_storage
from app.schemas.billing import (
    BillingAddressIn,
    BillingAddressOut,
    CancelSubscriptionResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceListOut,
    InvoiceOut,
    TaxInvoiceListOut,
    TaxInvoiceOut,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from app.schemas.platform import BillingCurrentOut, PublicPlanOut

log = structlog.get_logger(__name__)

router = APIRouter()

_ACTIVE_RAZORPAY_STATUSES = ("created", "authenticated", "active", "pending")


def _unix_to_iso(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat() if value else None


async def _active_subscription(db: AsyncSession, org_id) -> Subscription | None:
    return await db.scalar(
        select(Subscription).where(Subscription.org_id == org_id, Subscription.deleted_at.is_(None))
    )


@router.get("/enabled")
async def get_billing_enabled(token: TokenPayload = Depends(get_current_user)):
    """Whether credits and payments are in force (settings.BILLING_ENABLED) — the
    dashboard hides its Billing pages and the "subscription inactive" banner when not."""
    return {"enabled": settings.BILLING_ENABLED}


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
    # Keyed by org, not IP -- these are already admin-authenticated, so the
    # realistic risk is a compromised/malicious account hammering Razorpay's
    # API through us, not anonymous abuse.
    await enforce_rate_limit("billing-checkout", str(token.org_id), limit=10, window_seconds=3600)

    plan = await db.get(Plan, body.plan_id)
    if not plan or not plan.is_active:
        raise NotFoundError("Plan not found")
    if plan.is_custom_pricing:
        raise ConflictError("This plan has custom pricing — contact sales instead of checking out")

    org_for_billing_check = await db.get(Organization, token.org_id)
    if not org_for_billing_check or not org_for_billing_check.billing_state:
        # Needed to decide CGST+SGST vs IGST on the GST tax invoice generated
        # once payment confirms (app/core/invoicing.py) -- Indian GST law
        # bases that on the customer's own state, so it must be collected
        # before money changes hands, not guessed at afterward.
        raise ConflictError("Add your billing address before checking out (PUT /billing/address)")

    try:
        razorpay_plan_id = await sync_plan_to_razorpay(plan)
        # Not just "was empty" -- sync_plan_to_razorpay can also return a freshly
        # recreated id when the previously-cached one turned out to be stale
        # (e.g. a test-mode id that no longer exists under live-mode keys), and
        # that refreshed id must overwrite the stale one in the DB too.
        if plan.razorpay_plan_id != razorpay_plan_id:
            plan.razorpay_plan_id = razorpay_plan_id
            await db.commit()
    except RazorpayError as exc:
        raise ConflictError(str(exc))

    effective_price = plan.discount_price_minor if plan.discount_price_minor is not None else plan.price_minor
    sub = await _active_subscription(db, token.org_id)

    try:
        if sub and sub.provider == "razorpay" and sub.status in _ACTIVE_RAZORPAY_STATUSES:
            # Already has a mandate authorized — try to change the plan in
            # place, no new Checkout/authorization needed. Two known reasons
            # this in-place update can legitimately fail, both handled by
            # falling back to the same cancel-and-recreate flow a first-time
            # subscriber goes through instead of failing the upgrade outright:
            #   - UPI/eMandate subscriptions reject it ("cannot be updated
            #     when payment mode is upi") — confirmed against a real
            #     account, a hard platform restriction, not workaroundable.
            #   - "the id provided is invalid or could not be found" — the
            #     stored provider_subscription_id doesn't exist under the
            #     currently-configured Razorpay keys (e.g. after switching
            #     from test-mode to live-mode keys, subscriptions created
            #     under the old keys are gone as far as the new ones are
            #     concerned).
            try:
                await razorpay_update_subscription_plan(sub.provider_subscription_id, razorpay_plan_id)
                # This call itself is Razorpay's confirmation -- schedule_change_at:
                # "now" charges the existing mandate synchronously, no separate
                # Checkout/authorization step the customer could cancel out of
                # (unlike the fresh-subscription branch below), so it's safe to
                # apply the plan change immediately. Blend the remaining period's
                # credits the same way the superadmin manual plan-change path
                # does (app/api/platform.py) instead of just switching straight
                # to the new plan's fresh allotment and losing whatever of the
                # old plan's the org hadn't used yet this period.
                org = await db.get(Organization, token.org_id)
                if org:
                    await reset_credit_period_if_stale(db, org)
                    old_plan = await db.get(Plan, sub.plan_id)
                    sub.prorated_credits_override = compute_blended_monthly_credits(
                        old_plan_credits=old_plan.credits_per_month if old_plan else plan.credits_per_month,
                        new_plan_credits=plan.credits_per_month,
                        period_start=org.last_credit_reset_at,
                        now=datetime.now(timezone.utc),
                    )
                sub.plan_id = plan.id
                await db.commit()
                return CheckoutResponse(
                    action="change",
                    plan_name=plan.name,
                    amount_minor=effective_price,
                    currency=plan.currency,
                )
            except RazorpayError as exc:
                exc_str = str(exc).lower()
                _needs_fresh_subscription = (
                    "cannot be updated when payment mode is" in exc_str
                    or "id provided is invalid" in exc_str
                    or "could not be found" in exc_str
                    # Our own DB still has status="active" (that's what got us into
                    # this branch), but Razorpay's actual state disagrees -- seen live
                    # on a subscription left over from before a test/live-mode key
                    # switch, where our webhook never got a corresponding status
                    # update. Same fallback as the other two cases: stop trusting the
                    # stale subscription and get the customer a fresh one.
                    or "not in authenticated or active state" in exc_str
                )
                if not _needs_fresh_subscription:
                    raise
                log.info(
                    "razorpay_plan_change_requires_new_subscription",
                    org_id=str(token.org_id), subscription_id=sub.provider_subscription_id,
                )
                try:
                    await razorpay_cancel_subscription(sub.provider_subscription_id)
                except RazorpayError as cancel_exc:
                    log.warning(
                        "razorpay_old_subscription_cancel_failed",
                        subscription_id=sub.provider_subscription_id, error=str(cancel_exc),
                    )

        # First-time (or non-Razorpay, or UPI-plan-change-fallback) subscription:
        # create a fresh Razorpay Subscription and open Checkout to authorize
        # the recurring mandate.
        razorpay_sub = await razorpay_create_subscription(razorpay_plan_id=razorpay_plan_id, org_id=str(token.org_id))
    except RazorpayError as exc:
        raise ConflictError(str(exc))

    if sub:
        # plan_id deliberately stays on the OLD (already-paid-for) plan here --
        # this subscription isn't authorized yet, the customer is about to see
        # the Razorpay Checkout modal and can still cancel or fail the payment.
        # pending_plan_id records the target plan; the webhook promotes it to
        # plan_id (with blended credit proration) only once payment actually
        # confirms (_promote_pending_plan in app/api/webhooks.py). This was the
        # actual bug: plan_id used to be overwritten right here, before the
        # customer had even seen the payment screen.
        sub.pending_plan_id = plan.id
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
    await enforce_rate_limit("billing-verify-payment", str(token.org_id), limit=20, window_seconds=3600)

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
    await enforce_rate_limit("billing-cancel", str(token.org_id), limit=5, window_seconds=3600)

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


@router.get("/invoices", response_model=InvoiceListOut)
async def list_invoices(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Past invoices for the org's Razorpay subscription, fetched live from
    Razorpay rather than mirrored into our own DB -- Razorpay already is the
    source of truth for what was actually charged, and mirroring would mean
    another thing to keep in sync via webhooks we don't currently handle
    (invoice.paid etc.). Empty list (not an error) if there's no Razorpay
    subscription yet, or if the Razorpay call itself fails -- an invoice
    history that's temporarily unavailable shouldn't break the billing page.
    """
    sub = await _active_subscription(db, token.org_id)
    if not sub or sub.provider != "razorpay" or not sub.provider_subscription_id:
        return InvoiceListOut(invoices=[])

    try:
        raw_invoices = await list_subscription_invoices(sub.provider_subscription_id)
    except RazorpayError as exc:
        log.warning("billing_invoice_list_failed", org_id=str(token.org_id), error=str(exc))
        return InvoiceListOut(invoices=[])

    invoices = [
        InvoiceOut(
            id=inv["id"],
            amount_minor=inv.get("amount") or 0,
            currency=inv.get("currency") or "INR",
            status=inv.get("status") or "unknown",
            issued_at=_unix_to_iso(inv.get("issued_at")),
            hosted_url=inv.get("short_url"),
        )
        for inv in raw_invoices
    ]
    invoices.sort(key=lambda i: i.issued_at or "", reverse=True)
    return InvoiceListOut(invoices=invoices)


@router.get("/address", response_model=BillingAddressOut)
async def get_billing_address(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, token.org_id)
    if not org:
        raise NotFoundError("Organization not found")
    return BillingAddressOut(
        address_line=org.billing_address_line,
        city=org.billing_city,
        state=org.billing_state,
        pincode=org.billing_pincode,
        gstin=org.billing_gstin,
    )


@router.put("/address", response_model=BillingAddressOut)
async def save_billing_address(
    body: BillingAddressIn,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, token.org_id)
    if not org:
        raise NotFoundError("Organization not found")

    org.billing_address_line = body.address_line
    org.billing_city = body.city
    org.billing_state = body.state
    org.billing_pincode = body.pincode
    org.billing_gstin = body.gstin
    await db.commit()

    return BillingAddressOut(
        address_line=org.billing_address_line,
        city=org.billing_city,
        state=org.billing_state,
        pincode=org.billing_pincode,
        gstin=org.billing_gstin,
    )


@router.get("/tax-invoices", response_model=TaxInvoiceListOut)
async def list_tax_invoices(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    QuickHowl's own generated GST tax invoices (app/core/invoicing.py) --
    distinct from GET /invoices above, which shows Razorpay's own
    auto-generated ones. One of these exists per successful charge from the
    point the org's billing address was on file onward; earlier charges (or
    orgs that haven't set an address yet) simply have none here yet.
    """
    result = await db.execute(
        select(Invoice).where(Invoice.org_id == token.org_id).order_by(Invoice.issued_at.desc())
    )
    rows = result.scalars().all()
    return TaxInvoiceListOut(
        invoices=[
            TaxInvoiceOut(
                id=str(inv.id),
                invoice_number=inv.invoice_number,
                plan_name=inv.plan_name,
                total_minor=inv.total_minor,
                currency=inv.currency,
                issued_at=inv.issued_at.isoformat(),
            )
            for inv in rows
        ]
    )


@router.get("/tax-invoices/{invoice_id}/pdf")
async def download_tax_invoice(
    invoice_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.org_id != token.org_id:
        raise NotFoundError("Invoice not found")

    data = await get_storage().download(settings.BUCKET_INVOICES, invoice.storage_key)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )
