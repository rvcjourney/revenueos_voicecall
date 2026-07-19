"""add sarvam to ck_agent_templates_voice_provider constraint

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-17
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_templates_voice_provider", "agent_templates")
    op.create_check_constraint(
        "ck_agent_templates_voice_provider",
        "agent_templates",
        "voice_provider IN ('elevenlabs', 'cartesia', 'deepgram', 'chatterbox', 'sarvam')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_templates_voice_provider", "agent_templates")
    op.create_check_constraint(
        "ck_agent_templates_voice_provider",
        "agent_templates",
        "voice_provider IN ('elevenlabs', 'cartesia', 'deepgram', 'chatterbox')",
    )
