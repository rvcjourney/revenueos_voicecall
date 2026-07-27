"""
app/models/agent_access.py — Agent access request model.

Members request access to an AI Agent template; admin approves or rejects.
Only approved agents can be used in a member's campaign.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import TimestampMixin


class AgentAccessRequest(Base, TimestampMixin):
    __tablename__ = "agent_access_requests"
    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_agent_access_agent_user"),
        # Named to match the hand-written 0004 migration (shortened "agent_access"
        # prefix, not the tablename-derived "agent_access_requests" autogenerate default).
        Index("ix_agent_access_agent_id", "agent_id"),
        Index("ix_agent_access_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    agent_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    # Admin can grant edit rights on top of use rights
    can_edit: Mapped[bool] = mapped_column(nullable=False, server_default="false")
