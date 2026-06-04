"""add notes column to campaigns

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("notes", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "notes")
