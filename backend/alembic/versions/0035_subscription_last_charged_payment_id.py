"""subscriptions.last_charged_payment_id

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-24

Idempotency key for the Razorpay "subscription.charged" webhook handler
(app/api/webhooks.py) -- a redelivered event for an already-processed
payment previously re-zeroed credits_used_this_period a second time.
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("last_charged_payment_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "last_charged_payment_id")
