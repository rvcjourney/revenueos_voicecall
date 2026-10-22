"""Sarvam-only agents: default values for an agent's {placeholders}

- agent_templates.variables: {"partnerName": "Acme", ...}
- agent_templates.voice_id now defaults to "" (the language's default Sarvam voice)

Columns of removed features (pipeline, voice_provider, llm_model, is_prime,
pitch_structure, inbound/prompt-library/company-profile tables, ...) are left
in place untouched: the code no longer reads them, and no data is deleted.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("variables", JSONB(), nullable=False, server_default="{}"))
    op.alter_column("agent_templates", "voice_id", server_default="")


def downgrade() -> None:
    op.alter_column("agent_templates", "voice_id", server_default="C8R8ahkE5XosZ8qPpSPy")
    op.drop_column("agent_templates", "variables")
