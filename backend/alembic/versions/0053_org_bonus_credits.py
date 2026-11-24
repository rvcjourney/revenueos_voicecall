"""organizations.bonus_credits_this_period: minutes a SuperAdmin added on top of the plan

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("bonus_credits_this_period", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("organizations", "bonus_credits_this_period")
