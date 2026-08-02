"""
app/models/voice_clone_request.py — VoiceCloneRequest model.

A consent/approval gate in front of ClonedVoice creation: an org admin submits
a voice sample + a consent video (proof of authorization to clone that voice),
which sits here as "pending" until a platform superadmin reviews it. Only on
approval does the real ElevenLabs clone_voice() call happen and a ClonedVoice
row get created (see app/api/platform.py) — a not-yet-approved request never
has a usable voice_id anywhere in the system.

Deliberately a separate table from ClonedVoice rather than a new status value
on it: existing cloned voices are never touched, and nothing that queries
ClonedVoice needs to learn about a "pending" state that was never usable.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin


class VoiceCloneRequest(Base, OrgScopedMixin, TimestampMixin):
    """A pending/approved/rejected voice-cloning submission awaiting superadmin review."""
    __tablename__ = "voice_clone_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Persisted sample — needed at approval time to actually call ElevenLabs
    # (today's flow discards the sample bytes right after the inline clone
    # call; here cloning is deferred, so the bytes must survive until then).
    audio_sample_key: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_sample_file_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    audio_sample_content_type: Mapped[str] = mapped_column(String(100), nullable=False, server_default="audio/mpeg")

    # Consent video — proof of authorization, reviewed visually by the superadmin
    consent_video_key: Mapped[str] = mapped_column(String(500), nullable=False)
    consent_video_file_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    consent_video_content_type: Mapped[str] = mapped_column(String(100), nullable=False, server_default="video/webm")

    # pending | approved | rejected — plain String (not SAEnum) to match the
    # AgentAccessRequest/AgentCreationRequest convention used for review-queue
    # status columns elsewhere in this codebase.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending", index=True)

    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_admin_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set once approved and the real ClonedVoice row + ElevenLabs voice exist
    cloned_voice_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cloned_voices.id", ondelete="SET NULL"),
        nullable=True,
    )
