"""
app/models/invoice.py — Locally-generated GST tax invoices.

Distinct from Razorpay's own auto-generated invoices (app/core/razorpay_client.py
list_subscription_invoices, still shown separately) -- these are QuickHowl's
own branded, GST-compliant PDF tax invoices, generated the moment a Razorpay
subscription.charged webhook confirms a payment (app/core/invoicing.py),
stored in BUCKET_INVOICES, and listed/downloadable on the Billing page.
Numbered sequentially per calendar year (INV-{year}-{seq}) via InvoiceCounter,
which is incremented under SELECT...FOR UPDATE so concurrent webhook
deliveries can never hand out the same number twice.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base


class InvoiceCounter(Base):
    """One row per calendar year. last_seq is incremented under a row lock
    (see app/core/invoicing.py:_next_invoice_number) -- never read/incremented
    without first taking that lock, or two concurrent webhook deliveries could
    hand out the same invoice number."""
    __tablename__ = "invoice_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        UniqueConstraint("razorpay_payment_id", name="uq_invoices_razorpay_payment_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    # The Razorpay payment this invoice documents -- unique so a retried
    # webhook delivery for the same charge can never double-invoice it (see
    # generate_invoice_for_charge's existing-row check in invoicing.py).
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False)

    # Snapshot at time of issue -- the plan's name/price/credits can change
    # later, but this invoice must keep reflecting exactly what was charged
    # that cycle, not whatever the plan looks like today.
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credits_per_month: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    cgst_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sgst_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    igst_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")

    customer_state: Mapped[str] = mapped_column(String(100), nullable=False)
    place_of_supply: Mapped[str] = mapped_column(String(100), nullable=False)

    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
