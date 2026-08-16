"""clear cached razorpay_plan_id so new checkouts price in 18% GST

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-16

Business decision: every new checkout should charge 18% GST on top of the
plan's list price. app/core/razorpay_client.py:sync_plan_to_razorpay() now
bakes that into the Razorpay Plan resource it creates -- but Razorpay Plans
are immutable, and that function reuses plans.razorpay_plan_id whenever it's
already set (see its docstring). Every plan already has a cached id pointing
at the old, non-GST Razorpay Plan, so without this, sync_plan_to_razorpay()
would keep silently reusing those and no checkout would ever pick up GST.

Nulling this column forces the next checkout for each plan to create a fresh
GST-inclusive Razorpay Plan. Existing active subscribers are untouched --
their Subscription already references its own razorpay_subscription_id, which
keeps billing at its original (pre-GST) rate until they explicitly change
plans, same grandfathering behavior this column already relies on for any
other price change.
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE plans SET razorpay_plan_id = NULL WHERE razorpay_plan_id IS NOT NULL")


def downgrade() -> None:
    # Cleared ids are not recoverable -- the next checkout after a downgrade
    # will simply create fresh (non-GST) Razorpay Plans the same way.
    pass
