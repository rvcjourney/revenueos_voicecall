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

    # ── Credit-based billing (1 credit = 1 minute of call time) ────────────────
    # Monthly allotment of call-minutes included in the plan price.
    credits_per_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default="500")
    # USD cents charged per additional minute once an org exceeds credits_per_month
    # in its current billing period. See app/core/credits.py for the usage/overage math.
    credit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")

    # Feature gates, keyed by convention (see app/core/plan_features.py):
    #   allowed_voice_providers: list[str] — subset of app.models.agent.VoiceProvider values
    #   voice_cloning: bool — can this plan's orgs create ElevenLabs cloned voices
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── Marketing/pricing-card display (superadmin-editable, no deploy needed) ─
    # When set, the current "sale" price shown to customers; price_minor is
    # still shown struck through alongside it. Null = no discount.
    discount_price_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When true, the pricing card shows "Custom" / "Custom volume" instead of
    # price_minor/credits_per_month — those two columns become sort-order
    # sentinels only, never rendered. Used for a "Contact Sales" tier.
    is_custom_pricing: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # "Most Popular" badge on the marketing pricing card.
    is_highlighted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Free-form marketing copy bullets shown on the pricing card — display
    # only, unrelated to the plan-gating `features` dict above.
    marketing_bullets: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Mirrors this plan's current price as a Razorpay Plan object (see
    # app/core/razorpay_client.py). Razorpay Plans are immutable, so this id
    # stays pinned to whatever price was active when it was created — a later
    # price/discount change creates a NEW Razorpay Plan (existing subscribers
    # keep their original rate until they explicitly change plans). Null for
    # is_custom_pricing plans, which have no fixed price to subscribe to.
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
