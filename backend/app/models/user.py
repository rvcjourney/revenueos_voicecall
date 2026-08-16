"""
app/models/user.py — Organization and User models.
Organization is the top-level tenant; every other table has an org_id FK.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
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
    __table_args__ = (
        # Named to match the hand-written 0001 migration, which created this as a
        # separate object from the ix_organizations_slug unique index below.
        UniqueConstraint("slug", name="uq_organizations_slug"),
    )

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

    # Platform-level suspend/activate toggle (SuperAdmin). Distinct from deleted_at:
    # suspension is reversible and doesn't remove the org's data or history.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

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

    # ── Credit-based billing (1 credit = 1 minute of call time) ────────────────
    # Independent of the legacy calls_used_this_period/monthly_call_quota fields
    # above. Incremented in app/workers/tasks/campaign.py when a call ends; reset
    # to 0 (with last_credit_reset_at bumped to now) once the period is >30 days
    # old — see app/core/credits.py:reset_credit_period_if_stale().
    credits_used_this_period: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_credit_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Platform-level override: force ElevenLabs off for this org even if its plan
    # allows it (cost control / abuse response). Plan-level gating still applies —
    # both must be true for ElevenLabs to be usable (see app/core/plan_features.py).
    elevenlabs_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── GST tax-invoice billing details ─────────────────────────────────────
    # Collected via PUT /billing/address (app/api/billing.py) before checkout
    # is allowed — billing_state is what app/core/invoicing.py uses to decide
    # CGST+SGST (customer in the same state we're registered in) vs IGST
    # (any other state), which Indian GST law bases on the customer's state,
    # not ours. billing_gstin is optional — a B2B customer's own GSTIN,
    # printed on the invoice so they can claim input tax credit.
    billing_address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
    __table_args__ = (
        # Named to match the hand-written 0001 migration, which created this as a
        # separate object from the ix_users_email unique index below.
        UniqueConstraint("email", name="uq_users_email"),
    )

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
    # NULL = signup OTP not yet confirmed (see app/core/supabase_otp.py) — login is blocked until set.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users", foreign_keys="User.org_id"
    )
    assigned_trunks: Mapped[list["UserSipTrunk"]] = relationship(
        "UserSipTrunk", back_populates="user", foreign_keys="UserSipTrunk.user_id"
    )
