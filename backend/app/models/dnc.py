"""
app/models/dnc.py — Do Not Call lists.

Two separate tables:
  DoNotCallEntry  — org-specific DNC. Checked on every outbound dial within an org.
  SystemDncEntry  — global DNC (TRAI NCPR + admin blocks). Checked across ALL orgs.

Both are checked in the dispatcher before placing any call. The check order is:
  1. SystemDncEntry (global) — blocks regardless of org
  2. DoNotCallEntry (org-level) — blocks for that org only

TRAI NCPR compliance: SystemDncEntry is populated from TRAI's DND feed via a
Celery beat task (see workers/tasks/trai_ncpr.py, Phase 10). This is a legal
requirement under TRAI regulations for commercial voice communications in India.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class DNCReason(StrEnum):
    USER_REQUEST = "user_request"      # customer explicitly asked to stop calling
    WRONG_NUMBER = "wrong_number"      # number doesn't belong to intended party
    COMPLAINT = "complaint"            # customer filed a complaint
    MANUAL_BLOCK = "manual_block"      # admin manually blocked
    SPAM_REPORT = "spam_report"        # reported as spam


class SystemDNCSource(StrEnum):
    TRAI_NCPR = "trai_ncpr"            # India's National Customer Preference Register
    MANUAL_ADMIN = "manual_admin"      # blocked by platform admin
    GLOBAL_COMPLAINT = "global_complaint"  # complaint received at platform level


class DoNotCallEntry(Base, TimestampMixin):
    """
    Org-specific DNC. A number blocked in Org A can still be called by Org B.
    Unique constraint (org_id, phone_number) prevents duplicate entries per org.
    """
    __tablename__ = "do_not_call_entries"
    __table_args__ = (
        UniqueConstraint("org_id", "phone_number", name="uq_dnc_org_phone"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[DNCReason] = mapped_column(
        SAEnum(DNCReason, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
    )
    # Which call triggered this entry (null if added manually without a call)
    source_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Which user added this entry (null if added by automated system)
    added_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    source_call: Mapped["Call | None"] = relationship("Call")


class SystemDncEntry(Base, TimestampMixin):
    """
    Global DNC — applies to every org on the platform.
    phone_number is unique globally (same number can't appear twice in this table).
    imported_at tracks when the TRAI/admin import occurred (different from created_at
    which is when the row was written — they may differ on re-imports).
    """
    __tablename__ = "system_dnc_entries"
    __table_args__ = (
        # Named to match the hand-written 0001 migration, which created this as a
        # separate object from the ix_system_dnc_entries_phone_number unique index below.
        UniqueConstraint("phone_number", name="uq_system_dnc_entries_phone_number"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    source: Mapped[SystemDNCSource] = mapped_column(
        SAEnum(SystemDNCSource, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
    )
    # When this number was imported from the external feed (may predate row creation)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
