"""
app/models/call.py — Call, CallTranscript, and CallEvent models.

Call: one row per dial attempt. Append-only; never hard or soft deleted (legal/audit).
CallTranscript: one-to-one with Call; created after call ends via Celery task.
CallEvent: append-only audit log; one row per state transition or webhook event.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class CallDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallStatus(StrEnum):
    INITIATED = "initiated"     # room created, agent dispatched, SIP call being placed
    RINGING = "ringing"         # SIP INVITE sent, waiting for answer
    CONNECTED = "connected"     # call answered, agent session active
    COMPLETED = "completed"     # call ended normally
    NO_ANSWER = "no_answer"     # SIP 486/480/408/600/603 — not answered
    BUSY = "busy"               # SIP 486 specifically (line busy)
    FAILED = "failed"           # system error (SIP stack, LiveKit, agent crash)
    CANCELLED = "cancelled"     # cancelled before dialling (campaign stopped, DNC blocked)


class CallOutcome(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK_REQUESTED = "callback_requested"
    WRONG_NUMBER = "wrong_number"
    DO_NOT_CALL = "do_not_call"
    VOICEMAIL = "voicemail"
    PENDING = "pending"         # AI summary not yet generated


class CallSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Call(Base, TimestampMixin):
    """
    Permanent record of one dial attempt. Never deleted.
    org_id is denormalized from campaign to enable direct org-level queries
    without joining through campaigns.
    """
    __tablename__ = "calls"
    __table_args__ = (
        # Main dashboard query: calls for an org, newest first
        Index("ix_calls_org_started_at", "org_id", "started_at"),
        # Analytics: outcome breakdown by campaign
        Index("ix_calls_campaign_outcome", "campaign_id", "outcome"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # Denormalized from campaign for efficient org-level queries
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaign_contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    livekit_room_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    sip_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[CallDirection] = mapped_column(
        SAEnum(CallDirection, native_enum=False, values_callable=lambda x: [e.value for e in x], length=16),
        nullable=False,
        default=CallDirection.OUTBOUND,
        server_default=CallDirection.OUTBOUND,
    )
    status: Mapped[CallStatus] = mapped_column(
        SAEnum(CallStatus, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=CallStatus.INITIATED,
        server_default=CallStatus.INITIATED,
        index=True,
    )
    outcome: Mapped[CallOutcome] = mapped_column(
        SAEnum(CallOutcome, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=CallOutcome.PENDING,
        server_default=CallOutcome.PENDING,
        index=True,
    )

    # ── Timing ─────────────────────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Computed from answered_at → ended_at and stored for fast aggregation queries
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Billing: ₹/minute rate × duration_seconds / 60, rounded to 2 decimal places
    cost_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ── Post-call data (filled by generate_call_summary Celery task) ───────────
    recording_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[CallSentiment | None] = mapped_column(
        SAEnum(CallSentiment, native_enum=False, values_callable=lambda x: [e.value for e in x], length=16),
        nullable=True,
    )
    # Structured data extracted by LLM: {"products_mentioned": [...], "budget": ..., "decision_maker": bool}
    extracted_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    campaign: Mapped["Campaign | None"] = relationship("Campaign", back_populates="calls")
    transcript: Mapped["CallTranscript | None"] = relationship(
        "CallTranscript", back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    events: Mapped[list["CallEvent"]] = relationship(
        "CallEvent", back_populates="call", cascade="all, delete-orphan"
    )


class CallTranscript(Base):
    """
    One-to-one with Call. Created after call ends by the transcript_processor Celery task.
    full_text is the concatenated plain text for full-text search via GIN index.
    segments is the structured [{speaker, text, start_ms, end_ms}] JSON array.
    """
    __tablename__ = "call_transcripts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    segments: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Denormalized flat text for GIN full-text search index (see migration for index DDL)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    call: Mapped["Call"] = relationship("Call", back_populates="transcript")


class CallEvent(Base):
    """
    Append-only audit log for a call's state transitions and webhook payloads.
    event_type examples: "created", "dialing", "answered", "ended", "error",
                         "transcript_received", "summary_generated", "outcome_overridden"
    """
    __tablename__ = "call_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    call: Mapped["Call"] = relationship("Call", back_populates="events")
