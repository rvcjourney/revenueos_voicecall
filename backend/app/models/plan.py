"""
app/models/plan.py — Plan model.
Subscription tiers offered by the platform (Starter/Growth/Enterprise, etc).
Not org-scoped: plans are a shared catalog, referenced by subscriptions.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class Plan(Base, TimestampMixin):
    """A purchasable subscription tier. Money stored as integer minor units."""
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    monthly_call_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
