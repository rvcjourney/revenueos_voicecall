"""qwen/qwen3.6-27b is the only LLM model, platform-wide

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-14

Business decision: every agent (outbound AgentTemplate and inbound
InboundAgentTemplate, every org) now runs on qwen/qwen3.6-27b only.
Application-layer enforcement lives in app/schemas/agent.py and
app/schemas/inbound_agent.py (Literal type); this migration updates the
column defaults to match and backfills every existing row, so agents that
were previously configured with a different model switch over immediately
rather than only on next edit.
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_NEW_MODEL = "qwen/qwen3.6-27b"
_OLD_DEFAULT = "llama-3.1-8b-instant"


def upgrade() -> None:
    op.alter_column("agent_templates", "llm_model", server_default=_NEW_MODEL)
    op.alter_column("inbound_agent_templates", "llm_model", server_default=_NEW_MODEL)

    op.execute(f"UPDATE agent_templates SET llm_model = '{_NEW_MODEL}' WHERE llm_model <> '{_NEW_MODEL}'")
    op.execute(f"UPDATE inbound_agent_templates SET llm_model = '{_NEW_MODEL}' WHERE llm_model <> '{_NEW_MODEL}'")


def downgrade() -> None:
    op.alter_column("agent_templates", "llm_model", server_default=_OLD_DEFAULT)
    op.alter_column("inbound_agent_templates", "llm_model", server_default=_OLD_DEFAULT)
    # Backfilled rows are not reverted -- the pre-migration per-agent model
    # values are not recoverable from this migration alone.
