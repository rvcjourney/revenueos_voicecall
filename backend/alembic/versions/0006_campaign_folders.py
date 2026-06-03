"""add campaign_folders table and folder_id to campaigns

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_campaign_folders_org_id", "campaign_folders", ["org_id"])

    op.add_column(
        "campaigns",
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaign_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_campaigns_folder_id", "campaigns", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_folder_id", "campaigns")
    op.drop_column("campaigns", "folder_id")
    op.drop_index("ix_campaign_folders_org_id", "campaign_folders")
    op.drop_table("campaign_folders")
