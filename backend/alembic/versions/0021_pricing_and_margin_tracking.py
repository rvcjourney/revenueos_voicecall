"""pricing and margin tracking: plan discount/highlight/custom fields + platform_cost_settings

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-02

Adds superadmin-editable pricing-card fields to plans (discount override,
custom-pricing flag, highlighted flag, marketing bullet list) and a
singleton platform_cost_settings row holding the blended per-minute cost
estimate used to compute estimated gross margin on the platform analytics
page. See app/models/plan.py, app/models/platform_cost_settings.py,
app/api/platform.py, app/api/plans.py, app/api/billing.py.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("discount_price_minor", sa.Integer(), nullable=True))
    op.add_column(
        "plans", sa.Column("is_custom_pricing", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "plans", sa.Column("is_highlighted", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "plans",
        sa.Column(
            "marketing_bullets", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )

    op.create_table(
        "platform_cost_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cost_per_minute_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_platform_cost_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO platform_cost_settings (id, cost_per_minute_minor, currency) "
        "VALUES (1, 0, 'INR') ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("platform_cost_settings")
    op.drop_column("plans", "marketing_bullets")
    op.drop_column("plans", "is_highlighted")
    op.drop_column("plans", "is_custom_pricing")
    op.drop_column("plans", "discount_price_minor")
