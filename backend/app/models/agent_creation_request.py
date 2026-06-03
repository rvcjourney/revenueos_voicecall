"""
app/models/agent_creation_request.py — Member requests for a new AI Agent.

A member fills in company info + optional file; admin reviews and creates
the agent. Once created, admin links the new agent back to the request.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin


class AgentCreationRequest(Base, OrgScopedMixin, TimestampMixin):
    __tablename__ = "agent_creation_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # What the member wants
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_service: Mapped[str] = mapped_column(Text, nullable=False)
    target_customers: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional uploaded file (stored in MinIO)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # pending | reviewed
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
