"""agent_templates.transfer_number: who the agent's transfer_call tool rings

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("transfer_number", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("agent_templates", "transfer_number")
