"""prompt library: entries + version history, backfilled from existing agent templates

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-04

Adds prompt_library_entries (reusable, admin-curated system prompts — see
app/models/prompt_library.py) and prompt_library_versions (edit history).

Data migration: every existing, non-deleted agent_templates row with a
non-blank system_prompt gets a matching prompt_library_entries row
(source_agent_id linked back to it) plus an initial v1 prompt_library_versions
row, so prompts that already existed before this feature are visible in the
library without any manual re-entry. Tags are a best-effort keyword extraction
from the agent's name/description — admins can edit them afterwards. New
agents created after this migration are pulled in via
POST /api/prompt-library/sync-from-agents (see app/api/prompt_library.py).
"""
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from uuid6 import uuid7

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with",
    "your", "our", "is", "are", "new", "demo", "help", "helps", "using",
    "agent", "agents", "ai", "assistant", "bot", "template", "voice",
    "call", "calls", "calling", "caller",
    "customer", "customers", "lead", "leads", "service", "services",
    "team", "company", "sales", "rep", "representative", "support",
}


def _derive_tags(*texts: str | None, limit: int = 4) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for word in re.findall(r"[A-Za-z]+", text.lower()):
            if len(word) < 3 or word in _STOPWORDS or word in seen:
                continue
            seen.add(word)
            tags.append(word)
            if len(tags) >= limit:
                return tags
    return tags


def upgrade() -> None:
    op.create_table(
        "prompt_library_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("raw_input", sa.Text(), nullable=True),
        sa.Column("structured_prompt", sa.Text(), nullable=False),
        sa.Column("is_high_performing", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_agent_id"], ["agent_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_agent_id", name="uq_prompt_library_entries_source_agent"),
    )
    op.create_index(op.f("ix_prompt_library_entries_org_id"), "prompt_library_entries", ["org_id"], unique=False)
    op.create_index(op.f("ix_prompt_library_entries_created_by_id"), "prompt_library_entries", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_prompt_library_entries_source_agent_id"), "prompt_library_entries", ["source_agent_id"], unique=False)
    op.create_index(op.f("ix_prompt_library_entries_deleted_at"), "prompt_library_entries", ["deleted_at"], unique=False)
    op.create_index(
        "ix_prompt_library_entries_tags_gin", "prompt_library_entries", ["tags"],
        unique=False, postgresql_using="gin",
    )

    op.create_table(
        "prompt_library_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("structured_prompt", sa.Text(), nullable=False),
        sa.Column("editor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["prompt_library_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "version", name="uq_prompt_library_versions_entry_version"),
    )
    op.create_index(op.f("ix_prompt_library_versions_entry_id"), "prompt_library_versions", ["entry_id"], unique=False)

    # ── Data migration: backfill from existing agent templates ────────────────
    bind = op.get_bind()

    agent_templates = sa.table(
        "agent_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("org_id", postgresql.UUID(as_uuid=True)),
        sa.column("created_by_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("system_prompt", sa.Text),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    entries_table = sa.table(
        "prompt_library_entries",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("org_id", postgresql.UUID(as_uuid=True)),
        sa.column("created_by_id", postgresql.UUID(as_uuid=True)),
        sa.column("source_agent_id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String),
        sa.column("tags", postgresql.JSONB),
        sa.column("structured_prompt", sa.Text),
        sa.column("current_version", sa.Integer),
    )
    versions_table = sa.table(
        "prompt_library_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("entry_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer),
        sa.column("structured_prompt", sa.Text),
        sa.column("editor_id", postgresql.UUID(as_uuid=True)),
        sa.column("note", sa.String),
    )

    rows = bind.execute(
        sa.select(
            agent_templates.c.id,
            agent_templates.c.org_id,
            agent_templates.c.created_by_id,
            agent_templates.c.name,
            agent_templates.c.description,
            agent_templates.c.system_prompt,
        ).where(agent_templates.c.deleted_at.is_(None))
    ).fetchall()

    for row in rows:
        if not row.system_prompt or not row.system_prompt.strip():
            continue
        entry_id = uuid7()
        bind.execute(
            entries_table.insert().values(
                id=entry_id,
                org_id=row.org_id,
                created_by_id=row.created_by_id,
                source_agent_id=row.id,
                title=row.name,
                tags=_derive_tags(row.name, row.description),
                structured_prompt=row.system_prompt,
                current_version=1,
            )
        )
        bind.execute(
            versions_table.insert().values(
                id=uuid7(),
                entry_id=entry_id,
                version=1,
                structured_prompt=row.system_prompt,
                editor_id=row.created_by_id,
                note="Imported from existing agent",
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_prompt_library_versions_entry_id"), table_name="prompt_library_versions")
    op.drop_table("prompt_library_versions")

    op.drop_index("ix_prompt_library_entries_tags_gin", table_name="prompt_library_entries")
    op.drop_index(op.f("ix_prompt_library_entries_deleted_at"), table_name="prompt_library_entries")
    op.drop_index(op.f("ix_prompt_library_entries_source_agent_id"), table_name="prompt_library_entries")
    op.drop_index(op.f("ix_prompt_library_entries_created_by_id"), table_name="prompt_library_entries")
    op.drop_index(op.f("ix_prompt_library_entries_org_id"), table_name="prompt_library_entries")
    op.drop_table("prompt_library_entries")
