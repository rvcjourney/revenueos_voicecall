"""Add user_sip_trunks assignment table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-10
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sip_trunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sip_trunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_sip_trunks_user_id", "user_sip_trunks", ["user_id"])
    op.create_index("ix_user_sip_trunks_trunk_id", "user_sip_trunks", ["trunk_id"])
    op.create_unique_constraint(
        "uq_user_sip_trunks", "user_sip_trunks", ["user_id", "trunk_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_sip_trunks", "user_sip_trunks", type_="unique")
    op.drop_index("ix_user_sip_trunks_trunk_id", table_name="user_sip_trunks")
    op.drop_index("ix_user_sip_trunks_user_id", table_name="user_sip_trunks")
    op.drop_table("user_sip_trunks")
