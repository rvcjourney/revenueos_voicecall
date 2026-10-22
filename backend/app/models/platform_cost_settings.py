"""
app/models/platform_cost_settings.py — PlatformCostSettings model.

Singleton row (id is always 1, enforced by a CHECK constraint) holding the
platform-wide blended ₹/minute cost estimate used to compute estimated gross
margin on the SuperAdmin analytics page. Superadmin-editable via
PATCH /api/platform/settings/cost — see app/api/platform.py.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class PlatformCostSettings(Base, TimestampMixin):
    """Also the owner's platform-wide switches (calling engines), to avoid a
    second singleton table — read through app/core/pipelines.py's 60s cache."""
    __tablename__ = "platform_cost_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cost_per_minute_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    # NULL = same rate as cost_per_minute_minor.
    sarvam_cost_per_minute_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Kill-switch: off = no new call anywhere starts on the sarvam pipeline.
    sarvam_pipeline_global_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)
    # {language: {pipeline: {"enabled": bool, "tts_model": str, "voices": [ids]}}}
    language_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}", default=dict)
