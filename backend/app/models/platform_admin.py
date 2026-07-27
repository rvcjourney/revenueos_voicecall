"""
app/models/platform_admin.py — PlatformAdmin model.
The SuperAdmin tier: fully separate from Organization/User, sits outside org tenancy.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class PlatformAdmin(Base, TimestampMixin):
    """
    Platform-level operator account. Not org-scoped — manages the SaaS
    platform itself (billing, plans, cross-org support), not a tenant's data.
    """
    __tablename__ = "platform_admins"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
