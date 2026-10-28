"""leads + lead_activities: internal lead CRM

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custom_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_call_id", UUID(as_uuid=True), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_outcome", sa.String(32), nullable=True),
        sa.Column("last_summary", sa.Text, nullable=True),
        sa.Column("last_called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_status", sa.String(16), nullable=False, server_default="none"),
        sa.Column("meeting_at_text", sa.String(255), nullable=True),
        sa.Column("meeting_ref", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "phone", name="uq_leads_org_phone"),
    )
    op.create_index("ix_leads_org_id", "leads", ["org_id"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_owner_id", "leads", ["owner_id"])
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])
    op.create_index("ix_leads_org_last_called", "leads", ["org_id", "last_called_at"])

    op.create_table(
        "lead_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_activities_org_id", "lead_activities", ["org_id"])
    op.create_index("ix_lead_activities_lead_created", "lead_activities", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_table("lead_activities")
    op.drop_table("leads")
