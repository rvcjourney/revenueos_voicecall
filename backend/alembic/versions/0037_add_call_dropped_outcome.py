"""add call_dropped to ck_calls_outcome constraint

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-25

New CallOutcome value for a customer's line disconnecting abruptly
mid-conversation (see app/models/call.py's CallOutcome docstring and
agent/agent.py's abrupt_disconnect handling) -- distinct from
not_interested, since there's no real rejection signal, just a dropped call.
"""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_calls_outcome", "calls")
    op.create_check_constraint(
        "ck_calls_outcome",
        "calls",
        "outcome IN ('interested','not_interested','callback_requested',"
        "'wrong_number','do_not_call','voicemail','pending','no_answer','call_dropped')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_calls_outcome", "calls")
    op.create_check_constraint(
        "ck_calls_outcome",
        "calls",
        "outcome IN ('interested','not_interested','callback_requested',"
        "'wrong_number','do_not_call','voicemail','pending','no_answer')",
    )
