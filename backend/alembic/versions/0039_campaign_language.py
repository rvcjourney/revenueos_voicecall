"""campaigns.language: per-campaign spoken language

The agent template carries a language, but a campaign targeting (say) Tamil
Nadu needs to run the same agent in Tamil. NULL = use the template's language,
so every existing campaign keeps behaving exactly as before.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("language", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "language")
