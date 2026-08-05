"""
app/models/prompt_library.py — reusable, admin-curated system prompts.

A PromptLibraryEntry is either seeded from an existing AgentTemplate
(source_agent_id set, see alembic/versions/0022_prompt_library.py for the
one-time backfill of prompts that already existed) or created directly by an
admin from scratch. Content edits are versioned in PromptLibraryVersion so
admins can see history and roll back. is_high_performing is a manual flag any
org member can toggle based on real call outcomes — it is intentionally not
admin-gated like the rest of the entry.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class PromptLibraryEntry(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "prompt_library_entries"
    __table_args__ = (
        UniqueConstraint("source_agent_id", name="uq_prompt_library_entries_source_agent"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Set when this entry was backfilled/synced from an AgentTemplate. NULL for
    # library-only entries an admin wrote directly. Unique so an agent can only
    # back one entry — re-syncing updates it rather than duplicating.
    source_agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-form use-case labels ("paint", "laptop-repair") for grouping/search.
    # Auto-derived on import, admin-editable afterwards.
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_high_performing: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    versions: Mapped[list["PromptLibraryVersion"]] = relationship(
        "PromptLibraryVersion",
        back_populates="entry",
        order_by="PromptLibraryVersion.version.desc()",
        cascade="all, delete-orphan",
    )


class PromptLibraryVersion(Base):
    """Immutable snapshot of a PromptLibraryEntry.structured_prompt at a point in time."""
    __tablename__ = "prompt_library_versions"
    __table_args__ = (
        UniqueConstraint("entry_id", "version", name="uq_prompt_library_versions_entry_version"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prompt_library_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    editor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    entry: Mapped["PromptLibraryEntry"] = relationship("PromptLibraryEntry", back_populates="versions")
