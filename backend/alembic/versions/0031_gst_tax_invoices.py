"""GST tax invoices: org billing address + invoices/invoice_counters tables

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-16

Adds billing address fields to organizations (billing_state is what decides
CGST+SGST vs IGST on a generated invoice -- see app/core/invoicing.py) and two
new tables: invoice_counters (per-year sequence for INV-{year}-{seq} numbers)
and invoices (QuickHowl's own branded GST tax invoice, generated from the
Razorpay subscription.charged webhook -- app/api/webhooks.py). Distinct from
Razorpay's own auto-generated invoices, which are still fetched live and
shown separately (app/core/razorpay_client.py:list_subscription_invoices).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("billing_address_line", sa.String(length=255), nullable=True))
    op.add_column("organizations", sa.Column("billing_city", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("billing_state", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("billing_pincode", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("billing_gstin", sa.String(length=20), nullable=True))

    op.create_table(
        "invoice_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("year"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=64), nullable=False),
        sa.Column("invoice_number", sa.String(length=30), nullable=False),
        sa.Column("plan_name", sa.String(length=255), nullable=False),
        sa.Column("credits_per_month", sa.Integer(), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("cgst_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sgst_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("igst_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("customer_state", sa.String(length=100), nullable=False),
        sa.Column("place_of_supply", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        sa.UniqueConstraint("razorpay_payment_id", name="uq_invoices_razorpay_payment_id"),
    )
    op.create_index(op.f("ix_invoices_org_id"), "invoices", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoices_org_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("invoice_counters")

    op.drop_column("organizations", "billing_gstin")
    op.drop_column("organizations", "billing_pincode")
    op.drop_column("organizations", "billing_state")
    op.drop_column("organizations", "billing_city")
    op.drop_column("organizations", "billing_address_line")
