"""calls.recording_purged_at

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-24

Audit marker for app/workers/tasks/retention.py's daily purge of call
recordings/transcripts past CALL_DATA_RETENTION_DAYS. NULL = not purged yet
(or the call is still within the retention window); the Call row itself is
never deleted (see app/models/call.py's Call docstring) -- only its
recording_url and CallTranscript row.
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("recording_purged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "recording_purged_at")
