"""
app/models/sip.py — SIP trunk configuration per organization.
Multiple trunks per org are supported; one can be marked as is_default.
The SipTrunkResolver service selects the appropriate trunk per call.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, SoftDeleteMixin, TimestampMixin


class SipTransport(StrEnum):
    TCP = "tcp"
    UDP = "udp"
    TLS = "tls"


class SipTrunk(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
    """
    LiveKit outbound SIP trunk configuration.
    Soft-deleted to preserve audit history of which DID was used for historical calls.

    sip_password is stored as plaintext. Add column-level Fernet encryption
    (cryptography package) before exposing this table to untrusted operators.
    """
    __tablename__ = "sip_trunks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # LiveKit's identifier for this trunk (returned by CreateSIPOutboundTrunk)
    livekit_trunk_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sip_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    sip_username: Mapped[str] = mapped_column(String(255), nullable=False)
    sip_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # E.164 caller ID (DID) shown to the called party
    caller_id: Mapped[str] = mapped_column(String(20), nullable=False)
    transport: Mapped[SipTransport] = mapped_column(
        SAEnum(SipTransport, native_enum=False, values_callable=lambda x: [e.value for e in x], length=16),
        nullable=False,
        default=SipTransport.TCP,
        server_default=SipTransport.TCP,
    )
    # Only one trunk per org should have is_default=True.
    # Enforced in application logic (not DB constraint) to allow easy re-assignment.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="sip_trunks", foreign_keys="SipTrunk.org_id"
    )
