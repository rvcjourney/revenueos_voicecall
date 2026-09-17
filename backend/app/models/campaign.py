"""
app/models/campaign.py — Campaign and CampaignContact models.

Campaign: orchestrates a batch of outbound calls to a contact list.
CampaignContact: one row per phone number in the campaign; drives the dispatcher queue.
  - Hard-deleted (not soft): high volume (up to 50k rows/campaign), history lives in Calls.
  - FOR UPDATE SKIP LOCKED on (campaign_id, status) index drives safe multi-worker dispatch.
"""
from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, Time, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class CampaignGoal(StrEnum):
    LEAD_GENERATION = "lead_generation"
    FOLLOW_UP = "follow_up"
    SURVEY = "survey"
    ANNOUNCEMENT = "announcement"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ContactStatus(StrEnum):
    PENDING = "pending"
    DIALING = "dialing"       # currently being dialled; lock held by dispatcher
    COMPLETED = "completed"   # call reached an outcome (answered or no_answer)
    NO_ANSWER = "no_answer"   # awaiting retry (attempt_count < max_retries)
    FAILED = "failed"         # exhausted retries or system error
    DO_NOT_CALL = "do_not_call"  # blocked by org DNC or system DNC
    QUEUE_TIMEOUT = "queue_timeout"  # org was at its plan's concurrency cap past MAX_WAIT; retry pass picks it up


class CampaignFolder(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """Organizes campaigns under a company/client name. Soft-deleted; campaigns SET NULL on folder delete."""
    __tablename__ = "campaign_folders"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Campaign(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """
    Orchestrates a batch of outbound AI calls.
    Soft-deleted: spec requires "soft delete only if no active calls".
    Stats counters (interested_count, etc.) are updated atomically via
    UPDATE campaigns SET interested_count = interested_count + 1 WHERE id = :id
    Never read-modify-write them in Python — concurrent workers would race.
    """
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_org_status", "org_id", "status"),
    )

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
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[CampaignGoal] = mapped_column(
        SAEnum(CampaignGoal, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=CampaignGoal.LEAD_GENERATION,
        server_default=CampaignGoal.LEAD_GENERATION,
    )
    agent_template_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaign_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Overrides org default SIP trunk if set
    sip_trunk_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sip_trunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Prime Calling: each contact gets an LLM-personalised prompt + welcome
    # message generated just before their call (see _prepare_prime_prompt in
    # app/workers/tasks/campaign.py). False = classic campaign, one agent prompt for all.
    is_prime: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=CampaignStatus.DRAFT,
        server_default=CampaignStatus.DRAFT,
        index=True,
    )

    # ── Aggregate counters (updated atomically, never via ORM read-modify-write) ─
    total_contacts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    interested_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # ── Schedule ────────────────────────────────────────────────────────────────
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Dispatcher only dials within [calling_window_start, calling_window_end] in `timezone`
    calling_window_start: Mapped[time] = mapped_column(
        Time, nullable=False, server_default="09:00:00"
    )
    calling_window_end: Mapped[time] = mapped_column(
        Time, nullable=False, server_default="19:00:00"
    )
    # JSON array of day codes: ["mon","tue","wed","thu","fri","sat","sun"]
    calling_days: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("""'["mon","tue","wed","thu","fri","sat"]'::jsonb"""),
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Asia/Kolkata"
    )

    # ── Rate control ────────────────────────────────────────────────────────────
    calls_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    retry_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")

    # ── Lifecycle timestamps (distinct from TimestampMixin's created_at/updated_at) ─
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="campaigns", foreign_keys="Campaign.org_id"
    )
    agent_template: Mapped["AgentTemplate"] = relationship(
        "AgentTemplate", back_populates="campaigns"
    )
    contacts: Mapped[list["CampaignContact"]] = relationship(
        "CampaignContact", back_populates="campaign", cascade="all, delete-orphan"
    )
    calls: Mapped[list["Call"]] = relationship("Call", back_populates="campaign")


class CampaignContact(Base, TimestampMixin):
    """
    One contact (phone number) within a campaign. Drives the dispatcher queue.
    Hard-deleted by design — high volume, history preserved in Call rows.

    The (campaign_id, status) composite index enables efficient FOR UPDATE SKIP LOCKED
    queries in the dispatcher, preventing multiple workers from picking the same contact.
    """
    __tablename__ = "campaign_contacts"
    __table_args__ = (
        # Primary dispatcher query: WHERE campaign_id = X AND status = 'pending' FOR UPDATE SKIP LOCKED
        Index("ix_campaign_contacts_campaign_status", "campaign_id", "status"),
        # DNC check query: WHERE org_id = X AND phone = Y
        Index("ix_campaign_contacts_org_phone", "org_id", "phone"),
        # The following two duplicate coverage already provided above / by the
        # index=True campaign_id column below, but were added by the 0009
        # "performance indexes" migration under a shortened "campaign_contact"
        # (singular) prefix. Kept here (redundant but real) so autogenerate
        # matches the live DB.
        Index("ix_campaign_contact_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_contact_campaign_created", "campaign_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    campaign_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized for query efficiency — avoids joining to campaigns on every DNC check
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Arbitrary columns from the uploaded CSV (sanitized; CSV injection stripped at import)
    custom_fields: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[ContactStatus] = mapped_column(
        SAEnum(ContactStatus, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=ContactStatus.PENDING,
        server_default=ContactStatus.PENDING,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Prime Calling (only set on contacts of is_prime campaigns) ──────────────
    # Generated once on first dial attempt and reused on retries.
    generated_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last generation failure (call still went out on the fallback prompt)
    prompt_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="contacts")
