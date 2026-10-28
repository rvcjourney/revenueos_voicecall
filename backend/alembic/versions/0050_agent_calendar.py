"""agent_templates.gcal_*: the Google Calendar an agent books meetings into during calls

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("gcal_refresh_token", sa.Text(), nullable=True))
    op.add_column("agent_templates", sa.Column("gcal_email", sa.String(255), nullable=True))
    op.add_column("agent_templates", sa.Column("gcal_settings", JSONB(), nullable=False, server_default="{}"))


def downgrade() -> None:
    for name in ("gcal_settings", "gcal_email", "gcal_refresh_token"):
        op.drop_column("agent_templates", name)
