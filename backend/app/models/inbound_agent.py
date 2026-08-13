"""
app/models/inbound_agent.py — InboundAgentTemplate (system prompt + voice
configuration for answering inbound calls).

Deliberately a separate table from AgentTemplate (app/models/agent.py) even
though the shape is nearly identical -- inbound agents are managed and
assigned to phone numbers independently of outbound campaign/test-call
agents, kept apart on purpose (see app/models/sip.py: SipTrunk.inbound_agent_template_id).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.agent import AgentLanguage, VoiceProvider
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class InboundAgentTemplate(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """Saved system prompt + voice configuration for answering inbound calls."""
    __tablename__ = "inbound_agent_templates"

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
    # Spoken as soon as the call connects, before the LLM takes over
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # ── Voice configuration ────────────────────────────────────────────────────
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
    # InboundAgentCreate/InboundAgentUpdate's Literal type in
    # app/schemas/inbound_agent.py).
    llm_model: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="qwen/qwen3.6-27b"
    )
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.7")
    max_call_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="600"
    )
