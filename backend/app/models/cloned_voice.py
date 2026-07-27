"""
app/models/cloned_voice.py — ClonedVoice model.

A Premium-plan feature: an org member submits a voice sample, which is sent to
the ElevenLabs Voice Cloning API (app/core/elevenlabs_voice.py) to create a
custom voice model. The returned ElevenLabs voice_id is stored here and can
then be used as AgentTemplate.voice_id (with voice_provider="elevenlabs") on
any agent template for that org — see app/core/plan_features.py for the
plan-gating check enforced at agent-template create/update time.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class ClonedVoiceStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class ClonedVoice(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """A custom ElevenLabs voice model cloned from a user-submitted sample."""
    __tablename__ = "cloned_voices"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ElevenLabs' own voice ID — pass this as AgentTemplate.voice_id to use the clone
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sample_file_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    status: Mapped[ClonedVoiceStatus] = mapped_column(
        SAEnum(ClonedVoiceStatus, native_enum=False, values_callable=lambda x: [e.value for e in x], length=16),
        nullable=False,
        default=ClonedVoiceStatus.READY,
        server_default=ClonedVoiceStatus.READY,
    )
