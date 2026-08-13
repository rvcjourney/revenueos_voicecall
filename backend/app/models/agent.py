"""
app/models/agent.py — AgentTemplate (saved system prompt + voice configuration).
Templates are org-scoped, soft-deleted, and referenced by campaigns.
The agent worker fetches the active template via GET /api/agents/{id}/runtime
using the agent_template_id injected into LiveKit room metadata at dispatch time.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class VoiceProvider(StrEnum):
    ELEVENLABS = "elevenlabs"
    CARTESIA   = "cartesia"
    DEEPGRAM   = "deepgram"
    CHATTERBOX = "chatterbox"
    SARVAM     = "sarvam"


class AgentLanguage(StrEnum):
    HINGLISH = "hinglish"
    HINDI = "hindi"
    ENGLISH = "english"
    MARATHI = "marathi"
    TAMIL = "tamil"
    TELUGU = "telugu"
    BENGALI = "bengali"
    GUJARATI = "gujarati"
    KANNADA = "kannada"
    PUNJABI = "punjabi"


class AgentTemplate(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """
    Saved system prompt + voice configuration for an agent persona.
    Campaigns reference a template; the agent worker loads it at call time.
    Soft-deleted: active campaigns referencing a deleted template continue to work
    (the FK uses RESTRICT — you cannot delete a template used by a running campaign).
    """
    __tablename__ = "agent_templates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[AgentLanguage] = mapped_column(
        SAEnum(AgentLanguage, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=AgentLanguage.HINGLISH,
        server_default=AgentLanguage.HINGLISH,
    )
    # Spoken at the start of every call before the LLM takes over
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Full system prompt sent to the LLM. May include persona, knowledge base, guardrails.
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # ── Voice configuration ────────────────────────────────────────────────────
    # ElevenLabs voice_id or Deepgram model identifier
    voice_id: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="C8R8ahkE5XosZ8qPpSPy", default="9BWtsMINqrJLrRacOk9x"
    )
    voice_provider: Mapped[VoiceProvider] = mapped_column(
        SAEnum(VoiceProvider, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=VoiceProvider.ELEVENLABS,
        server_default=VoiceProvider.ELEVENLABS,
    )

    # ── LLM configuration ─────────────────────────────────────────────────────
    # Platform-wide: "qwen/qwen3.6-27b" is the only allowed value (enforced by
    # AgentCreate/AgentUpdate's Literal type in app/schemas/agent.py) -- still a
    # plain string column since a DB CHECK constraint on this would need its own
    # migration to change if the platform's model choice ever changes again.
    llm_model: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="qwen/qwen3.6-27b"
    )
    # Stored as float; Groq/OpenAI APIs accept float. Range: 0.0–2.0.
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.7")
    # Hard limit; agent auto-hangs up after this many seconds regardless of conversation state
    max_call_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="600"
    )

    # Relationships
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="agent_template"
    )
