"""
app/models/agent.py — AgentTemplate: an agent's Greeting, Instructions, the
default values of their {placeholders}, language and voice. Org-scoped,
soft-deleted, referenced by campaigns. The dialler copies the filled-in text
into each call's job metadata (app/workers/tasks/campaign.py).
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


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
    An agent persona: Greeting + Instructions (with {placeholders}) + voice.
    Campaigns reference a template; the dialler fills it in for each call.
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
    # The Greeting: spoken word-for-word at the start of every call
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The Instructions sent to the LLM (markdown, with {placeholders})
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Default value per placeholder, {"partnerName": "Acme"}; a contact's CSV column wins
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}", default=dict)

    # Sarvam stock voice id, or the id of one of the org's Sarvam cloned voices
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False, server_default="", default="")
    # "Creativity" (0.0–2.0), mapped into the LLM's safe band at call time
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.7")
    # How fast the voice talks (Sarvam pace; 1.0 = normal)
    speech_pace: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    # Brochure emailed automatically when a customer agrees to receive it on a call
    # (agent tool send_brochure → app/workers/tasks/brochure.py). File lives in BUCKET_EXPORTS.
    brochure_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    brochure_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brochure_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brochure_email_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brochure_email_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Google Calendar the agent books meetings into live on a call (app/core/google_calendar.py).
    # Refresh token is Fernet-encrypted; settings = working hours, meeting length, timezone.
    gcal_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gcal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gcal_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}", default=dict)
    # Hard limit; agent auto-hangs up after this many seconds regardless of conversation state
    max_call_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="600"
    )

    # Relationships
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="agent_template"
    )
