"""set every plan's max_concurrent_calls to 1, now actually enforced

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-16

Business decision: concurrent-call capacity per org is now governed by
plans.max_concurrent_calls (already an admin-editable field on the
SuperAdmin > Plans screen, but previously ignored at enforcement time -- see
app/core/concurrency.py:resolve_org_max_concurrent). Founder wants every
plan reset to a conservative default of 1 immediately, then to set the real
per-plan limits by hand right after this deploys -- not derived from
whatever value happened to be sitting in the column already (most plans
never had a meaningful value here since it had no effect until now).
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE plans SET max_concurrent_calls = 1")


def downgrade() -> None:
    # Prior per-plan values are not recoverable -- this migration doesn't
    # attempt to restore them.
    pass
