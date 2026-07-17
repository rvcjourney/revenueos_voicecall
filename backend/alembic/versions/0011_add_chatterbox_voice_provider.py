"""add cartesia and chatterbox to ck_agent_templates_voice_provider constraint

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-17
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_templates_voice_provider", "agent_templates")
    op.create_check_constraint(
        "ck_agent_templates_voice_provider",
        "agent_templates",
        "voice_provider IN ('elevenlabs', 'cartesia', 'deepgram', 'chatterbox')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_templates_voice_provider", "agent_templates")
    op.create_check_constraint(
        "ck_agent_templates_voice_provider",
        "agent_templates",
        "voice_provider IN ('elevenlabs', 'deepgram')",
    )
