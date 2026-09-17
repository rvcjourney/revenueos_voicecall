"""
app/models/company_profile.py — OrgCompanyProfile model.

The org's own "who we are" profile for Prime Calling. One row per org. When a
Prime campaign dials a contact, this profile + that contact's CSV row (+ their
website summary) are sent to the LLM to write a personalised system prompt and
welcome message for that one call — see app/services/prime_prompt.py.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin


class OrgCompanyProfile(Base, OrgScopedMixin, TimestampMixin):
    """The calling organization's company info, used to personalise Prime Calling prompts."""
    __tablename__ = "org_company_profiles"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_org_company_profiles_org_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    what_we_offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_customers: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_complete(self) -> bool:
        """Minimum needed for the LLM to write a meaningful pitch."""
        return bool((self.company_name or "").strip() and (self.what_we_offer or "").strip())
