"""
app/models/subscription.py — Subscription model.
Links an Organization to the Plan it is currently on. Soft-deleted to keep
a full history of plan changes/cancellations per org.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Subscription(Base, TimestampMixin, SoftDeleteMixin):
    """
    Which org is on which plan. org_id is unique among non-deleted rows only
    (see alembic/versions/0027_subscriptions_partial_unique_org_id.py):
    one active subscription row per org, soft-delete + insert a new row to
    record a plan change.
    """
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "ix_subscriptions_org_id_active_unique",
            "org_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Set when a plan change happens mid-billing-period: a time-weighted blend of
    # the old and new plan's credits_per_month for the remainder of the current
    # period only (see app/core/billing.py:compute_blended_monthly_credits).
    # Cleared back to NULL whenever the credit period resets (org.last_credit_reset_at
    # rolls over), at which point the new plan's credits_per_month applies in full.
    prorated_credits_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
