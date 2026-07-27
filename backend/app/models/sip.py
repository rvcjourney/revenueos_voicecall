"""
app/models/sip.py — SIP trunk configuration per organization.
Multiple trunks per org are supported; one can be marked as is_default.
Admins assign trunks to individual users via the UserSipTrunk join table.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
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

    sip_password and vobiz_auth_token are encrypted at rest (Fernet, see
    app/core/crypto.py) — the *_encrypted mapped columns hold ciphertext only;
    the sip_password / vobiz_auth_token properties below decrypt on read and
    encrypt on write, so callers use them exactly like a plain string attribute.
    Never expose either property (or the *_encrypted columns) in an API response.
    """
    __tablename__ = "sip_trunks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    # org_id from OrgScopedMixin

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # LiveKit's identifier for this trunk (returned by CreateSIPOutboundTrunk)
    livekit_trunk_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sip_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    sip_username: Mapped[str] = mapped_column(String(255), nullable=False)
    # DB column name stays "sip_password" (pre-existing); Python attribute is
    # renamed so the `sip_password` property below can own that name instead.
    sip_password_encrypted: Mapped[str] = mapped_column("sip_password", Text, nullable=False)
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

    # ── Vobiz self-serve connect (app/api/sip_trunks.py POST /connect-vobiz) ────
    # The org's own Vobiz API auth_id/auth_token, used to validate DID ownership
    # and (later) manage the number via Vobiz's API. auth_id isn't secret on its
    # own (it's an account identifier, not a credential); auth_token is.
    vobiz_auth_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vobiz_auth_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def sip_password(self) -> str:
        from app.core.crypto import decrypt_value
        return decrypt_value(self.sip_password_encrypted)

    @sip_password.setter
    def sip_password(self, plaintext: str) -> None:
        from app.core.crypto import encrypt_value
        self.sip_password_encrypted = encrypt_value(plaintext)

    @property
    def vobiz_auth_token(self) -> str | None:
        from app.core.crypto import decrypt_value
        if self.vobiz_auth_token_encrypted is None:
            return None
        return decrypt_value(self.vobiz_auth_token_encrypted)

    @vobiz_auth_token.setter
    def vobiz_auth_token(self, plaintext: str | None) -> None:
        from app.core.crypto import encrypt_value
        self.vobiz_auth_token_encrypted = encrypt_value(plaintext) if plaintext is not None else None

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="sip_trunks", foreign_keys="SipTrunk.org_id"
    )
    user_assignments: Mapped[list["UserSipTrunk"]] = relationship(
        "UserSipTrunk", back_populates="trunk", foreign_keys="UserSipTrunk.trunk_id"
    )


class UserSipTrunk(Base, TimestampMixin):
    """
    Admin-controlled assignment of a SIP trunk (phone number) to a user.
    A user can only pick from their assigned trunks when creating a campaign.
    One trunk can be shared across multiple users; one user can have multiple trunks.
    """
    __tablename__ = "user_sip_trunks"
    __table_args__ = (
        UniqueConstraint("user_id", "trunk_id", name="uq_user_sip_trunks"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sip_trunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="assigned_trunks")
    trunk: Mapped["SipTrunk"] = relationship("SipTrunk", foreign_keys=[trunk_id], back_populates="user_assignments")
    assigned_by: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_by_id])
