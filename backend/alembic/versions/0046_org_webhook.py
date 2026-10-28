"""organizations.webhook_url / webhook_secret: per-org call-completed webhook

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("webhook_url", sa.String(1024), nullable=True))
    op.add_column("organizations", sa.Column("webhook_secret", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "webhook_secret")
    op.drop_column("organizations", "webhook_url")
