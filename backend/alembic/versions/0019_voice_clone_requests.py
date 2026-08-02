"""voice_clone_requests table (consent/approval gate before ClonedVoice creation)

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-02

Adds voice_clone_requests: an org admin submits a name + audio sample +
consent video; a platform superadmin approves (creating the real
ClonedVoice + ElevenLabs voice) or rejects (with a reason). No changes to
cloned_voices itself — existing rows are untouched.

See app/models/voice_clone_request.py, app/api/voice_cloning.py,
app/api/platform.py.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_clone_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("audio_sample_key", sa.String(length=500), nullable=False),
        sa.Column("audio_sample_file_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("audio_sample_content_type", sa.String(length=100), server_default="audio/mpeg", nullable=False),
        sa.Column("consent_video_key", sa.String(length=500), nullable=False),
        sa.Column("consent_video_file_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("consent_video_content_type", sa.String(length=100), server_default="video/webm", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloned_voice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_voice_clone_requests_status"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_admin_id"], ["platform_admins.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cloned_voice_id"], ["cloned_voices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_voice_clone_requests_org_id"), "voice_clone_requests", ["org_id"], unique=False)
    op.create_index(
        op.f("ix_voice_clone_requests_created_by_id"), "voice_clone_requests", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_voice_clone_requests_status"), "voice_clone_requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_voice_clone_requests_status"), table_name="voice_clone_requests")
    op.drop_index(op.f("ix_voice_clone_requests_created_by_id"), table_name="voice_clone_requests")
    op.drop_index(op.f("ix_voice_clone_requests_org_id"), table_name="voice_clone_requests")
    op.drop_table("voice_clone_requests")
