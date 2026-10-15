"""campaigns.pitch_structure + make agent_template_id optional

Prime campaigns no longer need a pre-saved AI Agent just to supply a system
prompt -- they can describe this specific campaign's pitch (what to say, in
what order, for this one client/business) directly, and that text becomes
the LLM's input for every contact's generated script instead of an agent
template's system prompt. agent_template_id becomes nullable so a Prime
campaign can be created without one (classic/non-prime campaigns still
require it -- enforced in the API, not the schema, since the requirement is
conditional on is_prime).

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("pitch_structure", sa.Text(), nullable=True))
    op.alter_column("campaigns", "agent_template_id", nullable=True)


def downgrade() -> None:
    op.alter_column("campaigns", "agent_template_id", nullable=False)
    op.drop_column("campaigns", "pitch_structure")
