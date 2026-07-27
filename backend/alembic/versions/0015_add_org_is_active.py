"""add is_active to organizations

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-26

Platform-level suspend/activate toggle used by the SuperAdmin API
(app/api/platform.py PATCH /orgs/{id}). Distinct from deleted_at: suspending
an org is reversible and doesn't remove its data or history.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("organizations", "is_active")
