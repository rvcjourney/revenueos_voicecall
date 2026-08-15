"""Add subscriptions.pending_plan_id

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-15

Holds the target plan for a self-serve plan change while it's awaiting
Razorpay Checkout payment confirmation -- plan_id itself now only moves once
the webhook confirms the payment (see app/api/webhooks.py:_promote_pending_plan).
Fixes a bug where cancelling/failing the Checkout modal still left the org
showing the new (unpaid) plan, because plan_id used to be written immediately
at checkout time instead of on payment confirmation.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("pending_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscriptions_pending_plan_id_plans",
        "subscriptions", "plans",
        ["pending_plan_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_subscriptions_pending_plan_id_plans", "subscriptions", type_="foreignkey")
    op.drop_column("subscriptions", "pending_plan_id")
