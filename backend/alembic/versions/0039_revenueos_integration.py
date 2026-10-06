"""RevenueOS Brain integration: client and launch bookkeeping

- revenueos_clients: one row per client_reference → the organization and
  admin user Brain created for that client.
- revenueos_launches: one row per campaign reference → the campaign it
  created and a hash of the request, so a repeated reference is recognised.

Only adds two new tables; no existing table or row is changed.

RLS enabled on both with no policies, same reasoning as 0025/0033.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revenueos_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_reference", sa.String(120), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("client_reference", name="uq_revenueos_clients_client_reference"),
        sa.UniqueConstraint("org_id", name="uq_revenueos_clients_org_id"),
    )
    op.create_index("ix_revenueos_clients_org_id", "revenueos_clients", ["org_id"])
    op.execute("ALTER TABLE revenueos_clients ENABLE ROW LEVEL SECURITY")

    op.create_table(
        "revenueos_launches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("revenueos_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("contacts_rejected", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_revenueos_launches_reference"),
    )
    op.create_index("ix_revenueos_launches_org_id", "revenueos_launches", ["org_id"])
    op.create_index("ix_revenueos_launches_client_id", "revenueos_launches", ["client_id"])
    op.create_index("ix_revenueos_launches_campaign_id", "revenueos_launches", ["campaign_id"])
    op.execute("ALTER TABLE revenueos_launches ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_revenueos_launches_campaign_id", table_name="revenueos_launches")
    op.drop_index("ix_revenueos_launches_client_id", table_name="revenueos_launches")
    op.drop_index("ix_revenueos_launches_org_id", table_name="revenueos_launches")
    op.drop_table("revenueos_launches")
    op.drop_index("ix_revenueos_clients_org_id", table_name="revenueos_clients")
    op.drop_table("revenueos_clients")
