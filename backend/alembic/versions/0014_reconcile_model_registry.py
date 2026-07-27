"""reconcile model registry

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-26

Registers agent_access_requests and agent_creation_requests in Base.metadata
(they existed in the DB via migrations 0004/0005 but were never imported in
app/models/__init__.py, so Alembic autogenerate previously proposed dropping
them). Also reconciles several ORM index/constraint names against objects
that were originally created by hand-written SQL/migrations under different
naming than SQLAlchemy's autogenerate default (see app/models/user.py,
call.py, campaign.py, dnc.py, agent_access.py for the __table_args__ this
corresponds to) — those are pure model-side renames with no DDL here.

The only real schema change in this migration: campaign_folders never got a
deleted_at index when it was created (migration 0006 omitted it), even though
every other soft-deleted table in this codebase has one. Adding it now for
consistency and query performance on the (already-used) is_deleted filter.
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_campaign_folders_deleted_at", "campaign_folders", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_campaign_folders_deleted_at", table_name="campaign_folders")
