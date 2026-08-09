"""email verification: users.email_verified_at

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-09

New signups must verify their email (via Supabase Auth OTP, see
app/core/supabase_otp.py) before they can log in. NULL = not verified yet;
existing users are backfilled to "now" so nobody already using the platform
gets locked out retroactively.
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET email_verified_at = now() WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
