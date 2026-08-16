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


class InvoiceOut(BaseModel):
    id: str
    amount_minor: int
    currency: str
    status: str
    issued_at: str | None = None  # ISO 8601, or null if Razorpay hasn't issued it yet
    hosted_url: str | None = None  # Razorpay-hosted page to view/download the invoice


class InvoiceListOut(BaseModel):
    invoices: list[InvoiceOut]


class BillingAddressIn(BaseModel):
    address_line: str | None = None
    city: str | None = None
    state: str  # required -- decides CGST+SGST vs IGST on generated tax invoices
    pincode: str | None = None
    gstin: str | None = None  # optional -- the org's own GSTIN, for their input tax credit


class BillingAddressOut(BaseModel):
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    gstin: str | None = None


class TaxInvoiceOut(BaseModel):
    id: str
    invoice_number: str
    plan_name: str
    total_minor: int
    currency: str
    issued_at: str  # ISO 8601


class TaxInvoiceListOut(BaseModel):
    invoices: list[TaxInvoiceOut]
