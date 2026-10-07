"""Move every agent to qwen/qwen3.8-27b

Groq no longer serves qwen/qwen3.6-27b ("model_not_found"), so the agent's
language model returned nothing and calls went silent after the greeting.
Same shape as 0028: new column defaults, and every existing row backfilled.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-07
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_NEW_MODEL = "qwen/qwen3.8-27b"
_OLD_MODEL = "qwen/qwen3.6-27b"


def upgrade() -> None:
    op.alter_column("agent_templates", "llm_model", server_default=_NEW_MODEL)
    op.alter_column("inbound_agent_templates", "llm_model", server_default=_NEW_MODEL)

    op.execute(f"UPDATE agent_templates SET llm_model = '{_NEW_MODEL}' WHERE llm_model <> '{_NEW_MODEL}'")
    op.execute(f"UPDATE inbound_agent_templates SET llm_model = '{_NEW_MODEL}' WHERE llm_model <> '{_NEW_MODEL}'")


def downgrade() -> None:
    op.alter_column("agent_templates", "llm_model", server_default=_OLD_MODEL)
    op.alter_column("inbound_agent_templates", "llm_model", server_default=_OLD_MODEL)
    # Backfilled rows are not reverted, as in 0028.
