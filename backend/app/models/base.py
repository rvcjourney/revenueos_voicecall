"""
app/models/base.py — Reusable SQLAlchemy 2.0 mixins.

Three mixins are available:
  TimestampMixin  — created_at, updated_at (server-side defaults)
  SoftDeleteMixin — deleted_at, is_deleted property
  OrgScopedMixin  — org_id FK; enforces multi-tenancy at the type level

Usage:
    class MyModel(Base, OrgScopedMixin, TimestampMixin, SoftDeleteMixin):
        __tablename__ = "my_models"
        ...

Mixin order convention: Base first, then OrgScopedMixin, TimestampMixin, SoftDeleteMixin last.
This keeps PK and business columns first in CREATE TABLE output.

Note on updated_at: onupdate=func.now() is client-side — it fires when SQLAlchemy
ORM issues an UPDATE. Raw SQL updates (psql, Alembic data migrations) bypass it.
For a fully server-side solution, add a PostgreSQL trigger via op.execute() in the migration.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds created_at and updated_at with server-side defaults."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Adds deleted_at for logical deletion.
    Service methods must include .where(Model.deleted_at.is_(None)) on every query.
    Hard DELETE is never issued on soft-delete tables.
    """
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class OrgScopedMixin:
    """
    Multi-tenancy enforcement at the type level.

    Every model inheriting this mixin has an org_id column that is:
    - NOT NULL (every row belongs to exactly one org)
    - Indexed (all service queries filter on org_id)
    - Cascade-deleted when the org is deleted

    Service layer rule: EVERY query on an OrgScoped model MUST include
    a .where(Model.org_id == current_org_id) filter. No exceptions.
    Use the get_org_scoped_query() helper in services to enforce this.
    """
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
