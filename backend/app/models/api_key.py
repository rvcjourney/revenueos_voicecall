"""
app/models/api_key.py — Programmatic API access keys.
Keys are never stored in plaintext — only the SHA-256 hash is persisted.
The full key is shown to the user once at creation time.
Revocation uses revoked_at (not hard delete) so audit logs remain intact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 hex of the full key ("motm_<32 random hex chars>"). 64 chars fixed length.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # First 12 chars of the full key — shown in the UI for identification (never the full key)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < datetime.now(timezone.utc)

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
