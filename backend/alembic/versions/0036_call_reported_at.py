"""calls.reported_at

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-24

Idempotency marker for POST /{id}/agent-report (app/api/calls.py) -- a
retried report (agent/agent.py's _post_agent_report backs off up to 3
attempts) previously could double-increment Campaign.interested_count and,
for inbound calls, double-bill credits / double-release the org's
concurrency slot.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "reported_at")
