"""Add can_edit flag to agent_access_requests

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_access_requests",
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("agent_access_requests", "can_edit")
