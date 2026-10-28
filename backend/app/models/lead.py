"""
app/models/lead.py — Internal lead CRM.

One Lead per (org, phone): the same person called from several campaigns is
one lead with one timeline. Leads are created/updated automatically from each
call's agent report (app/services/leads.py) and edited by the team in /leads.
Every change lands in LeadActivity, which is the lead's timeline.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    MEETING_SCHEDULED = "meeting_scheduled"
    QUALIFIED = "qualified"
    WON = "won"
    LOST = "lost"
    DO_NOT_CALL = "do_not_call"


class LeadEmailStatus(StrEnum):
    NONE = "none"
    CAPTURED = "captured"   # the customer gave an email on a call; nothing sent yet
    SENT = "sent"
    FAILED = "failed"
    REPLIED = "replied"     # a reply was found in the org's mailbox (IMAP)


class LeadMeetingStatus(StrEnum):
    NONE = "none"
    SCHEDULED = "scheduled"
    DONE = "done"
    CANCELLED = "cancelled"


class LeadActivityType(StrEnum):
    CALL = "call"
    NOTE = "note"
    STATUS_CHANGE = "status_change"
    EMAIL = "email"           # payload.kind "brochure" when sent automatically after a call
    EMAIL_REPLY = "email_reply"
    MEETING = "meeting"
    EDIT = "edit"
    IMPORT = "import"


class Lead(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("org_id", "phone", name="uq_leads_org_phone"),
        Index("ix_leads_org_last_called", "org_id", "last_called_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=LeadStatus.NEW, default=LeadStatus.NEW, index=True)
    owner_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    custom_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    # Denormalized from the latest call so the list page needs no joins.
    last_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True,
    )
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    email_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=LeadEmailStatus.NONE, default=LeadEmailStatus.NONE)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=LeadMeetingStatus.NONE, default=LeadMeetingStatus.NONE)
    # Free text on purpose: the agent books in natural language ("Tuesday 4pm").
    meeting_at_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LeadActivity(Base, OrgScopedMixin):
    __tablename__ = "lead_activities"
    __table_args__ = (Index("ix_lead_activities_lead_created", "lead_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    # None = done by the system / AI agent.
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
