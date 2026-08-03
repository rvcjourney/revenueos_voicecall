"""
app/schemas/billing.py — Pydantic schemas for tenant-facing billing/checkout
(app/api/billing.py). Separate from app/schemas/platform.py's PlanOut/
PublicPlanOut (superadmin/public plan catalog schemas).
"""
from __future__ import annotations

from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    plan_id: str


class CheckoutResponse(BaseModel):
    # "change" means an existing Razorpay subscription's plan was updated
    # in-place (no new Checkout/mandate needed); "new" means the frontend
    # must open Razorpay Checkout with subscription_id to authorize a mandate.
    action: str  # "new" | "change"
    subscription_id: str | None = None
    razorpay_key_id: str | None = None
    plan_name: str
    amount_minor: int
    currency: str


class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    verified: bool


class CancelSubscriptionResponse(BaseModel):
    status: str
