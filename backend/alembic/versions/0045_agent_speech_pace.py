"""agent_templates.speech_pace: per-agent speaking speed

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("speech_pace", sa.Float(), nullable=False, server_default="1.0"))


def downgrade() -> None:
    op.drop_column("agent_templates", "speech_pace")
