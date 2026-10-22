"""
app/models/cloned_voice.py — ClonedVoice model.

A Premium-plan feature: an org's voice sample is cloned on Sarvam once the
owner approves the request (app/api/platform.py). The returned voice id is
stored here and can be used as AgentTemplate.voice_id or Campaign.voice_id —
see app/core/plan_features.py check_voice_choice. Rows with provider
"elevenlabs" predate the Sarvam-only change and are no longer usable.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, synonym
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class ClonedVoiceStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class ClonedVoice(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """A custom voice cloned from a user-submitted sample."""
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
    # The provider's own voice ID (ElevenLabs id, or Sarvam "svc-..." when
    # provider == "sarvam") — pass this as AgentTemplate.voice_id to use the clone.
    # Column keeps its historical name; `provider_voice_id` is the neutral alias.
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_voice_id = synonym("elevenlabs_voice_id")
    provider: Mapped[str] = mapped_column(String(16), nullable=False, server_default="elevenlabs", default="sarvam")
    # Reference language the clone was recorded in; Sarvam's auto-transcript of it.
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_file_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    status: Mapped[ClonedVoiceStatus] = mapped_column(
        SAEnum(ClonedVoiceStatus, native_enum=False, values_callable=lambda x: [e.value for e in x], length=16),
        nullable=False,
        default=ClonedVoiceStatus.READY,
        server_default=ClonedVoiceStatus.READY,
    )
