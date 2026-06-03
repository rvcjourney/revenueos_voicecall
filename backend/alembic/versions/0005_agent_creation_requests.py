"""create agent_creation_requests table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_creation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("product_service", sa.Text, nullable=False),
        sa.Column("target_customers", sa.Text, nullable=False),
        sa.Column("key_points", sa.Text, nullable=False),
        sa.Column("file_key", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("admin_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending','reviewed')", name="ck_agent_creation_status"),
    )
    op.create_index("ix_agent_creation_requests_user_id", "agent_creation_requests", ["user_id"])
    op.create_index("ix_agent_creation_requests_org_id",  "agent_creation_requests", ["org_id"])


def downgrade() -> None:
    op.drop_table("agent_creation_requests")
