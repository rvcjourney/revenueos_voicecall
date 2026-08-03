"""razorpay billing: plans.razorpay_plan_id

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-03

Adds the Razorpay Plan mirror id to plans (null for is_custom_pricing plans,
which have no fixed price to subscribe to). Subscription.provider/
provider_customer_id/provider_subscription_id already exist (added in an
earlier migration, unused until now) and are reused as-is -- no new columns
needed there. See app/core/razorpay_client.py, app/api/billing.py,
app/api/webhooks.py.
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("razorpay_plan_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "razorpay_plan_id")
