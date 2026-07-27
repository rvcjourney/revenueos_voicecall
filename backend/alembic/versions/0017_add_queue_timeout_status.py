"""add queue_timeout to ck_campaign_contacts_status constraint

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-26

New ContactStatus.QUEUE_TIMEOUT (app/models/campaign.py): a contact that
waited longer than CONCURRENCY_MAX_WAIT_SECONDS for a plan-based org-level
call slot (app/core/concurrency.py) without ever being dialed. Picked back up
by the normal retry pass (app/workers/tasks/campaign.py _next_retry_batch).
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_campaign_contacts_status", "campaign_contacts")
    op.create_check_constraint(
        "ck_campaign_contacts_status",
        "campaign_contacts",
        "status IN ('pending', 'dialing', 'completed', 'no_answer', 'failed', 'do_not_call', 'queue_timeout')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_campaign_contacts_status", "campaign_contacts")
    op.create_check_constraint(
        "ck_campaign_contacts_status",
        "campaign_contacts",
        "status IN ('pending', 'dialing', 'completed', 'no_answer', 'failed', 'do_not_call')",
    )
