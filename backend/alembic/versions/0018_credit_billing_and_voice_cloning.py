"""credit billing (Plan/Organization/Subscription) + cloned_voices table

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-27

Adds:
  - plans.credits_per_month, plans.credit_price_cents
  - organizations.credits_used_this_period, organizations.last_credit_reset_at,
    organizations.elevenlabs_enabled
  - subscriptions.prorated_credits_override
  - cloned_voices table (ElevenLabs Voice Cloning — Premium plan feature)

See app/core/credits.py, app/core/billing.py, app/core/plan_features.py.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── plans ────────────────────────────────────────────────────────────────
    op.add_column(
        "plans",
        sa.Column("credits_per_month", sa.Integer(), server_default="500", nullable=False),
    )
    op.add_column(
        "plans",
        sa.Column("credit_price_cents", sa.Integer(), server_default="10", nullable=False),
    )

    # ── organizations ────────────────────────────────────────────────────────
    op.add_column(
        "organizations",
        sa.Column("credits_used_this_period", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "last_credit_reset_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("elevenlabs_enabled", sa.Boolean(), server_default="true", nullable=False),
    )

    # ── subscriptions ────────────────────────────────────────────────────────
    op.add_column(
        "subscriptions",
        sa.Column("prorated_credits_override", sa.Integer(), nullable=True),
    )

    # ── cloned_voices ────────────────────────────────────────────────────────
    op.create_table(
        "cloned_voices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("elevenlabs_voice_id", sa.String(length=100), nullable=False),
        sa.Column("sample_file_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="ready", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ready', 'failed')", name="ck_cloned_voices_status"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cloned_voices_org_id"), "cloned_voices", ["org_id"], unique=False)
    op.create_index(op.f("ix_cloned_voices_created_by_id"), "cloned_voices", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_cloned_voices_deleted_at"), "cloned_voices", ["deleted_at"], unique=False)
    op.create_index(
        op.f("ix_cloned_voices_elevenlabs_voice_id"), "cloned_voices", ["elevenlabs_voice_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cloned_voices_elevenlabs_voice_id"), table_name="cloned_voices")
    op.drop_index(op.f("ix_cloned_voices_deleted_at"), table_name="cloned_voices")
    op.drop_index(op.f("ix_cloned_voices_created_by_id"), table_name="cloned_voices")
    op.drop_index(op.f("ix_cloned_voices_org_id"), table_name="cloned_voices")
    op.drop_table("cloned_voices")

    op.drop_column("subscriptions", "prorated_credits_override")

    op.drop_column("organizations", "elevenlabs_enabled")
    op.drop_column("organizations", "last_credit_reset_at")
    op.drop_column("organizations", "credits_used_this_period")

    op.drop_column("plans", "credit_price_cents")
    op.drop_column("plans", "credits_per_month")
