"""
app/core/razorpay_client.py — Razorpay Subscriptions API helpers.

The installed `razorpay` SDK (v2.0.1, confirmed by introspecting the actual
package rather than trusting docs alone) is synchronous (built on `requests`),
so every call here runs via asyncio.to_thread to avoid blocking the event
loop.

Confirmed SDK method names/signatures (not guessed):
    client.plan.create(data)                              -> {"id": "plan_xxx", ...}
    client.subscription.create(data)                       -> {"id": "sub_xxx", "status": "created", ...}
        -- no customer_id param at creation: Razorpay auto-links/creates the
           Customer from the checkout form once the authorization payment
           completes, and the subscription's customer_id becomes readable
           afterward (e.g. in the webhook payload or via .fetch()).
    client.subscription.edit(subscription_id, data)        -> updated subscription dict (plan change)
    client.subscription.cancel(subscription_id, data)      -> cancelled subscription dict
    client.subscription.fetch(subscription_id)              -> subscription dict
    client.utility.verify_webhook_signature(body, signature, secret)
        -- body must be a str (SDK does bytes(body, "utf-8") internally), not bytes.
        -- raises razorpay.errors.SignatureVerificationError on mismatch.
    client.utility.verify_subscription_payment_signature({razorpay_subscription_id, razorpay_payment_id, razorpay_signature})
        -- secret defaults to the client's own key_secret; raises same error on mismatch.

Razorpay Plans are immutable once created -- syncing a changed price means
creating a NEW Razorpay Plan and returning its id; existing subscribers stay
on their original plan/rate until they explicitly change (grandfathering,
not a bug).
"""
from __future__ import annotations

import asyncio

import razorpay
import structlog
from razorpay.errors import SignatureVerificationError

from app.config import settings
from app.models.plan import Plan

log = structlog.get_logger(__name__)

# Effectively-indefinite monthly billing: 100 cycles ~= 8.3 years. Razorpay
# requires a finite total_count; we recreate/extend well before ever reaching it.
SUBSCRIPTION_TOTAL_COUNT = 100


class RazorpayError(Exception):
    """Raised for any Razorpay API/config failure. Message is safe to show the caller."""


def get_client() -> razorpay.Client:
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RazorpayError("Razorpay is not configured on this server")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


async def sync_plan_to_razorpay(plan: Plan) -> str:
    """
    Returns plan.razorpay_plan_id if already set AND still valid under the
    currently-configured Razorpay keys (verified with a fetch) -- Razorpay
    plans are immutable within a given account/mode, but a cached id from a
    different one (e.g. after switching from test-mode to live-mode keys)
    silently no longer exists even though the DB still has it. Creates a
    fresh Razorpay Plan otherwise. Caller is responsible for persisting the
    returned id onto `plan.razorpay_plan_id` and committing.
    """
    client = get_client()

    if plan.razorpay_plan_id:
        try:
            await asyncio.to_thread(client.plan.fetch, plan.razorpay_plan_id)
            return plan.razorpay_plan_id
        except Exception as exc:
            log.warning(
                "razorpay_cached_plan_id_invalid_recreating",
                plan_id=str(plan.id), razorpay_plan_id=plan.razorpay_plan_id, error=str(exc),
            )
            # fall through and create a fresh one below

    effective_price = plan.discount_price_minor if plan.discount_price_minor is not None else plan.price_minor
    try:
        result = await asyncio.to_thread(
            client.plan.create,
            {
                "period": "monthly",
                "interval": 1,
                "item": {
                    "name": f"QuickHowl {plan.name}",
                    "amount": effective_price,
                    "currency": plan.currency,
                    "description": f"QuickHowl {plan.name} plan — {plan.credits_per_month} min/month",
                },
                "notes": {"internal_plan_id": str(plan.id)},
            },
        )
    except Exception as exc:
        log.error("razorpay_plan_create_failed", plan_id=str(plan.id), error=str(exc))
        raise RazorpayError(f"Could not create Razorpay plan: {exc}")
    return result["id"]


async def create_subscription(*, razorpay_plan_id: str, org_id: str) -> dict:
    client = get_client()
    try:
        return await asyncio.to_thread(
            client.subscription.create,
            {
                "plan_id": razorpay_plan_id,
                "total_count": SUBSCRIPTION_TOTAL_COUNT,
                "customer_notify": True,
                "notes": {"org_id": org_id},
            },
        )
    except Exception as exc:
        log.error("razorpay_subscription_create_failed", org_id=org_id, error=str(exc))
        raise RazorpayError(f"Could not create Razorpay subscription: {exc}")


async def update_subscription_plan(subscription_id: str, new_razorpay_plan_id: str) -> dict:
    client = get_client()
    try:
        return await asyncio.to_thread(
            client.subscription.edit,
            subscription_id,
            {"plan_id": new_razorpay_plan_id, "schedule_change_at": "now"},
        )
    except Exception as exc:
        log.error("razorpay_subscription_edit_failed", subscription_id=subscription_id, error=str(exc))
        raise RazorpayError(f"Could not change Razorpay subscription plan: {exc}")


async def cancel_subscription(subscription_id: str) -> dict:
    client = get_client()
    try:
        return await asyncio.to_thread(
            client.subscription.cancel,
            subscription_id,
            {"cancel_at_cycle_end": True},
        )
    except Exception as exc:
        log.error("razorpay_subscription_cancel_failed", subscription_id=subscription_id, error=str(exc))
        raise RazorpayError(f"Could not cancel Razorpay subscription: {exc}")


async def fetch_subscription(subscription_id: str) -> dict:
    client = get_client()
    try:
        return await asyncio.to_thread(client.subscription.fetch, subscription_id)
    except Exception as exc:
        log.error("razorpay_subscription_fetch_failed", subscription_id=subscription_id, error=str(exc))
        raise RazorpayError(f"Could not fetch Razorpay subscription: {exc}")


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    Raises RazorpayError on a bad/missing signature; returns True on success.
    The SDK requires body as a str (it does bytes(body, "utf-8") internally),
    so raw_body is decoded here -- passing bytes directly raises a TypeError.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise RazorpayError("RAZORPAY_WEBHOOK_SECRET is not configured on this server")
    client = get_client()
    try:
        return client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
        )
    except SignatureVerificationError:
        raise RazorpayError("Invalid webhook signature")


def verify_subscription_payment_signature(
    *, razorpay_subscription_id: str, razorpay_payment_id: str, razorpay_signature: str
) -> bool:
    client = get_client()
    try:
        return client.utility.verify_subscription_payment_signature(
            {
                "razorpay_subscription_id": razorpay_subscription_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
    except SignatureVerificationError:
        raise RazorpayError("Invalid payment signature")
