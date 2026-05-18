"""add no_answer to ck_calls_outcome constraint

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-18
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_calls_outcome", "calls")
    op.create_check_constraint(
        "ck_calls_outcome",
        "calls",
        "outcome IN ('interested','not_interested','callback_requested',"
        "'wrong_number','do_not_call','voicemail','pending','no_answer')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_calls_outcome", "calls")
    op.create_check_constraint(
        "ck_calls_outcome",
        "calls",
        "outcome IN ('interested','not_interested','callback_requested',"
        "'wrong_number','do_not_call','voicemail','pending')",
    )
