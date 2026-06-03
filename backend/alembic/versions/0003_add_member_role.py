"""add member to ck_users_role constraint

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','member','manager','agent')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','manager','agent')",
    )
