"""agent_templates.language: allow every Sarvam language

The 0001 check only allowed hinglish/hindi/english/marathi, so saving an agent in
Telugu, Tamil, ... failed with a 500. The app already validates the language (the
AgentLanguage enum and pipelines.validate), so the DB check is dropped.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-24
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_templates_language", "agent_templates", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_agent_templates_language", "agent_templates",
        "language IN ('hinglish', 'hindi', 'english', 'marathi')",
    )
