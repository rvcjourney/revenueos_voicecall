"""Two calling pipelines: "standard" (existing) and "sarvam" (all-Sarvam live call)

- pipeline on agent templates, inbound agent templates (default "standard"),
  campaigns (nullable override) and calls (what the call actually ran on)
- org flags: sarvam_pipeline_enabled, default_pipeline, sarvam_cloning_allowed
- cloned voices / clone requests: provider (+ language, Sarvam transcript)
- owner switches on the existing platform_cost_settings singleton row
- calls: pipeline_fallback + per-call latency aggregates; campaigns: pause_reason

Every existing row keeps meaning exactly what it meant before ("standard",
"elevenlabs"), so no customer sees a change until the owner flips a flag.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("agent_templates", "inbound_agent_templates"):
        op.add_column(table, sa.Column("pipeline", sa.String(16), nullable=False, server_default="standard"))
    op.add_column("campaigns", sa.Column("pipeline", sa.String(16), nullable=True))
    op.add_column("campaigns", sa.Column("pause_reason", sa.String(64), nullable=True))

    op.add_column("calls", sa.Column("pipeline", sa.String(16), nullable=True))
    op.add_column("calls", sa.Column("pipeline_fallback", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("calls", sa.Column("latency_metrics", JSONB(), nullable=True))

    op.add_column("organizations", sa.Column("sarvam_pipeline_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organizations", sa.Column("default_pipeline", sa.String(16), nullable=False, server_default="standard"))
    op.add_column("organizations", sa.Column("sarvam_cloning_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("cloned_voices", sa.Column("provider", sa.String(16), nullable=False, server_default="elevenlabs"))
    op.add_column("cloned_voices", sa.Column("language", sa.String(32), nullable=True))
    op.add_column("cloned_voices", sa.Column("reference_text", sa.Text(), nullable=True))
    op.add_column("voice_clone_requests", sa.Column("provider", sa.String(16), nullable=False, server_default="elevenlabs"))
    op.add_column("voice_clone_requests", sa.Column("language", sa.String(32), nullable=True))

    op.add_column("platform_cost_settings", sa.Column("sarvam_pipeline_global_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("platform_cost_settings", sa.Column("language_overrides", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("platform_cost_settings", sa.Column("sarvam_cost_per_minute_minor", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ("sarvam_cost_per_minute_minor", "language_overrides", "sarvam_pipeline_global_enabled"):
        op.drop_column("platform_cost_settings", col)
    for col in ("language", "provider"):
        op.drop_column("voice_clone_requests", col)
    for col in ("reference_text", "language", "provider"):
        op.drop_column("cloned_voices", col)
    for col in ("sarvam_cloning_allowed", "default_pipeline", "sarvam_pipeline_enabled"):
        op.drop_column("organizations", col)
    for col in ("latency_metrics", "pipeline_fallback", "pipeline"):
        op.drop_column("calls", col)
    op.drop_column("campaigns", "pause_reason")
    op.drop_column("campaigns", "pipeline")
    for table in ("inbound_agent_templates", "agent_templates"):
        op.drop_column(table, "pipeline")
