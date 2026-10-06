"""Rename campaigns → voice_campaigns

The voice tables now live in a database shared with other RevenueOS tools,
one of which already owns a table called `campaigns`.

Postgres keeps foreign keys, indexes and RLS attached across a rename. The
primary key is renamed too because its index name (campaigns_pkey) would
clash with the other table's; other index and constraint names are kept.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-06
"""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("campaigns", "voice_campaigns")
    op.execute("ALTER TABLE voice_campaigns RENAME CONSTRAINT campaigns_pkey TO voice_campaigns_pkey")


def downgrade() -> None:
    op.execute("ALTER TABLE voice_campaigns RENAME CONSTRAINT voice_campaigns_pkey TO campaigns_pkey")
    op.rename_table("voice_campaigns", "campaigns")
