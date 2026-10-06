"""
app/models/revenueos.py — Bookkeeping for the RevenueOS Brain integration.

RevenueOSClient: one row per client_reference → the organization and admin
  user Brain created for that client. The integration routes only ever reach
  an organization through this table, so the key cannot touch an org it did
  not create.
RevenueOSLaunch: one row per campaign reference → the campaign it created,
  plus a hash of the request content so a repeated reference is recognised
  (same content: duplicate; different content: refused).

See app/integrations/revenueos.py.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin


class RevenueOSClient(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "revenueos_clients"
    __table_args__ = (
        UniqueConstraint("client_reference", name="uq_revenueos_clients_client_reference"),
        UniqueConstraint("org_id", name="uq_revenueos_clients_org_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    client_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


class RevenueOSLaunch(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "revenueos_launches"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_revenueos_launches_reference"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    client_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("revenueos_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("voice_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # sha256 of the request content that identifies this campaign (see
    # app/integrations/revenueos.py::content_hash for what is and isn't included)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # [{"phone": ..., "reason": ...}] from the original request, so a repeat
    # can return the same answer without re-validating.
    contacts_rejected: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
