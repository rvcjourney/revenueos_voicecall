"""inbound calling: inbound_agent_templates table + sip_trunks inbound columns

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-02

Adds inbound_agent_templates (a separate table from agent_templates, kept
apart from outbound campaign/test-call agents on purpose) plus nullable
inbound-* columns on sip_trunks recording which agent answers a number's
inbound calls and the Vobiz/LiveKit resource ids created to route it there.
Also adds calls.sip_trunk_id -- inbound calls have no campaign to resolve
Vobiz credentials through the way outbound calls do, so the Call row itself
must record which trunk answered it (set by app/api/agent_internal.py).

See app/models/inbound_agent.py, app/models/sip.py, app/models/call.py,
app/api/sip_trunks.py, app/api/inbound_agents.py, app/api/agent_internal.py.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_agent_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=32), server_default="hinglish", nullable=False),
        sa.Column("welcome_message", sa.Text(), server_default="", nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("voice_id", sa.String(length=100), server_default="C8R8ahkE5XosZ8qPpSPy", nullable=False),
        sa.Column("voice_provider", sa.String(length=32), server_default="elevenlabs", nullable=False),
        sa.Column("llm_model", sa.String(length=100), server_default="llama-3.1-8b-instant", nullable=False),
        sa.Column("llm_temperature", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("max_call_duration_seconds", sa.Integer(), server_default="600", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inbound_agent_templates_org_id"), "inbound_agent_templates", ["org_id"], unique=False
    )
    op.create_index(
        op.f("ix_inbound_agent_templates_created_by_id"), "inbound_agent_templates", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_inbound_agent_templates_deleted_at"), "inbound_agent_templates", ["deleted_at"], unique=False
    )

    op.add_column("sip_trunks", sa.Column("inbound_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column(
        "sip_trunks", sa.Column("inbound_agent_template_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("sip_trunks", sa.Column("vobiz_inbound_trunk_id", sa.String(length=100), nullable=True))
    op.add_column("sip_trunks", sa.Column("livekit_inbound_trunk_id", sa.String(length=100), nullable=True))
    op.add_column("sip_trunks", sa.Column("livekit_inbound_dispatch_rule_id", sa.String(length=100), nullable=True))
    op.create_foreign_key(
        "fk_sip_trunks_inbound_agent_template_id",
        "sip_trunks",
        "inbound_agent_templates",
        ["inbound_agent_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("calls", sa.Column("sip_trunk_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_calls_sip_trunk_id"), "calls", ["sip_trunk_id"], unique=False)
    op.create_foreign_key(
        "fk_calls_sip_trunk_id", "calls", "sip_trunks", ["sip_trunk_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_calls_sip_trunk_id", "calls", type_="foreignkey")
    op.drop_index(op.f("ix_calls_sip_trunk_id"), table_name="calls")
    op.drop_column("calls", "sip_trunk_id")

    op.drop_constraint("fk_sip_trunks_inbound_agent_template_id", "sip_trunks", type_="foreignkey")
    op.drop_column("sip_trunks", "livekit_inbound_dispatch_rule_id")
    op.drop_column("sip_trunks", "livekit_inbound_trunk_id")
    op.drop_column("sip_trunks", "vobiz_inbound_trunk_id")
    op.drop_column("sip_trunks", "inbound_agent_template_id")
    op.drop_column("sip_trunks", "inbound_enabled")

    op.drop_index(op.f("ix_inbound_agent_templates_deleted_at"), table_name="inbound_agent_templates")
    op.drop_index(op.f("ix_inbound_agent_templates_created_by_id"), table_name="inbound_agent_templates")
    op.drop_index(op.f("ix_inbound_agent_templates_org_id"), table_name="inbound_agent_templates")
    op.drop_table("inbound_agent_templates")
