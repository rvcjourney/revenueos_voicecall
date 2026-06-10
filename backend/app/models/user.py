"""
app/models/user.py — Organization and User models.
Organization is the top-level tenant; every other table has an org_id FK.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"   # sales team — limited access
    MANAGER = "manager"
    AGENT = "agent"


class Organization(Base, TimestampMixin, SoftDeleteMixin):
    """
    Top-level tenant. All other org-scoped tables FK to this.
    Soft-deleted (never hard-deleted) for compliance and audit trail.
    """
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, server_default="")

    # Default SIP trunk for this org. FK added via ALTER TABLE in Alembic migration
    # because it creates a circular dependency (organizations → sip_trunks → organizations).
    sip_trunk_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "sip_trunks.id",
            use_alter=True,
            name="fk_organizations_default_sip_trunk",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    # E.164 caller ID used on outbound calls when no trunk-specific caller_id is set
    sip_caller_id: Mapped[str] = mapped_column(String(20), nullable=False, server_default="")

    # ── Quota tracking ─────────────────────────────────────────────────────────
    plan_tier: Mapped[str] = mapped_column(String(50), nullable=False, server_default="starter")
    monthly_call_quota: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    # Updated atomically: UPDATE organizations SET calls_used_this_period = calls_used_this_period + 1
    # Redis caches the remaining quota per org (key: motm:quota:{org_id}) with a short TTL.
    calls_used_this_period: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    billing_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + INTERVAL '30 days'"),
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="organization", foreign_keys="User.org_id"
    )
    sip_trunks: Mapped[list["SipTrunk"]] = relationship(
        "SipTrunk", back_populates="organization", foreign_keys="SipTrunk.org_id"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign", back_populates="organization", foreign_keys="Campaign.org_id"
    )


class User(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """
    Application user. Soft-deleted for GDPR compliance and audit trail.
    Passwords are stored as bcrypt hashes (cost=12). Never store plaintext.
    """
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, values_callable=lambda x: [e.value for e in x], length=32),
        nullable=False,
        default=UserRole.AGENT,
        server_default=UserRole.AGENT,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users", foreign_keys="User.org_id"
    )
    assigned_trunks: Mapped[list["UserSipTrunk"]] = relationship(
        "UserSipTrunk", back_populates="user", foreign_keys="UserSipTrunk.user_id"
    )
