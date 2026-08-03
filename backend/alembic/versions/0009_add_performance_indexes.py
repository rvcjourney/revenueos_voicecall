"""Add performance indexes for high-frequency queries

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-12
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_call_phone_number", "calls", ["phone_number"])
    op.create_index("ix_call_campaign_id", "calls", ["campaign_id"])
    op.create_index("ix_call_org_created", "calls", ["org_id", "created_at"])
    op.create_index(
        "ix_campaign_contact_campaign_status",
        "campaign_contacts",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_campaign_contact_campaign_created",
        "campaign_contacts",
        ["campaign_id", "created_at"],
    )
    op.create_index("ix_call_started_at", "calls", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_call_started_at", "calls")
    op.drop_index("ix_campaign_contact_campaign_created", "campaign_contacts")
    op.drop_index("ix_campaign_contact_campaign_status", "campaign_contacts")
    op.drop_index("ix_call_org_created", "calls")
    op.drop_index("ix_call_campaign_id", "calls")
    op.drop_index("ix_call_phone_number", "calls")
