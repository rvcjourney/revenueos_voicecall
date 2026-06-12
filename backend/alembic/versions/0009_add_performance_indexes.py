"""Add performance indexes for high-frequency queries

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # call(phone_number) — webhook phone lookup (_find_call_by_phone scans this)
    op.create_index("ix_call_phone_number", "call", ["phone_number"])

    # call(campaign_id) — list calls by campaign (GET /api/calls?campaign_id=...)
    op.create_index("ix_call_campaign_id", "call", ["campaign_id"])

    # call(org_id, created_at) — org-scoped call history (list_calls endpoint)
    op.create_index("ix_call_org_created", "call", ["org_id", "created_at"])

    # campaign_contact(campaign_id, status) — batch picking in dispatcher (_next_pending_batch)
    op.create_index(
        "ix_campaign_contact_campaign_status",
        "campaign_contact",
        ["campaign_id", "status"],
    )

    # campaign_contact(campaign_id, created_at) — FIFO ordering in _next_pending_batch
    op.create_index(
        "ix_campaign_contact_campaign_created",
        "campaign_contact",
        ["campaign_id", "created_at"],
    )

    # call(started_at) — recording webhook time-window lookup
    op.create_index("ix_call_started_at", "call", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_call_started_at", "call")
    op.drop_index("ix_campaign_contact_campaign_created", "campaign_contact")
    op.drop_index("ix_campaign_contact_campaign_status", "campaign_contact")
    op.drop_index("ix_call_org_created", "call")
    op.drop_index("ix_call_campaign_id", "call")
    op.drop_index("ix_call_phone_number", "call")
