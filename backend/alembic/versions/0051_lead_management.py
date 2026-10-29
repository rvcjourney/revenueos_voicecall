"""leads: next follow-up, priority, source, row note

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("priority", sa.String(8), nullable=True))
    op.add_column("leads", sa.Column("priority_by_user", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("leads", sa.Column("source", sa.String(16), nullable=False, server_default="manual"))
    op.add_column("leads", sa.Column(
        "source_campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("leads", sa.Column("note", sa.Text(), nullable=True))
    op.create_index("ix_leads_org_follow_up", "leads", ["org_id", "next_follow_up_at"])

    # Existing leads: the campaign that first called them, else an import, else typed in by hand.
    op.execute("""
        UPDATE leads l SET source = 'campaign', source_campaign_id = (
            SELECT c.campaign_id FROM calls c
            WHERE c.org_id = l.org_id AND c.phone_number = l.phone AND c.campaign_id IS NOT NULL
            ORDER BY c.created_at LIMIT 1)
        WHERE EXISTS (
            SELECT 1 FROM calls c
            WHERE c.org_id = l.org_id AND c.phone_number = l.phone AND c.campaign_id IS NOT NULL)
    """)
    op.execute("""
        UPDATE leads l SET source = 'import'
        WHERE l.source = 'manual' AND EXISTS (
            SELECT 1 FROM lead_activities a WHERE a.lead_id = l.id AND a.type = 'import')
    """)
    op.execute("UPDATE leads SET priority = 'hot' WHERE status IN ('interested', 'meeting_scheduled', 'qualified')")


def downgrade() -> None:
    op.drop_index("ix_leads_org_follow_up", table_name="leads")
    for name in ("note", "source_campaign_id", "source", "priority_by_user", "priority", "next_follow_up_at"):
        op.drop_column("leads", name)
