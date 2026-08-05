from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import NotFoundError, ValidationError as AppValidationError
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.prompt_library import PromptLibraryEntry, PromptLibraryVersion
from app.models.user import User
from app.schemas.prompt_library import (
    MarkPerformingRequest,
    PromptLibraryCreate,
    PromptLibraryEntryOut,
    PromptLibraryListResponse,
    PromptLibraryUpdate,
    PromptLibraryVersionOut,
    SyncFromAgentsResponse,
)
from app.services.prompt_library import derive_tags_from_text

log = logging.getLogger(__name__)

router = APIRouter()


# ── Output builders (batch-fetch related names to avoid N+1 queries) ─────────

async def _entries_to_out(db: AsyncSession, entries: list[PromptLibraryEntry]) -> list[PromptLibraryEntryOut]:
    user_ids = {e.created_by_id for e in entries if e.created_by_id}
    agent_ids = {e.source_agent_id for e in entries if e.source_agent_id}

    users_map: dict[UUID, str] = {}
    if user_ids:
        rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))).all()
        users_map = {r.id: r.full_name for r in rows}

    agents_map: dict[UUID, str] = {}
    if agent_ids:
        rows = (await db.execute(select(AgentTemplate.id, AgentTemplate.name).where(AgentTemplate.id.in_(agent_ids)))).all()
        agents_map = {r.id: r.name for r in rows}

    return [
        PromptLibraryEntryOut(
            id=str(e.id),
            title=e.title,
            tags=list(e.tags or []),
            raw_input=e.raw_input,
            structured_prompt=e.structured_prompt,
            is_high_performing=e.is_high_performing,
            current_version=e.current_version,
            source_agent_id=str(e.source_agent_id) if e.source_agent_id else None,
            source_agent_name=agents_map.get(e.source_agent_id) if e.source_agent_id else None,
            created_by_id=str(e.created_by_id) if e.created_by_id else None,
            created_by_name=users_map.get(e.created_by_id, "Unknown") if e.created_by_id else "Unknown",
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in entries
    ]


async def _entry_to_out(db: AsyncSession, entry: PromptLibraryEntry) -> PromptLibraryEntryOut:
    return (await _entries_to_out(db, [entry]))[0]


async def _get_org_entry(db: AsyncSession, entry_id: UUID, org_id: UUID) -> PromptLibraryEntry:
    entry = await db.get(PromptLibraryEntry, entry_id)
    if not entry or entry.org_id != org_id or entry.deleted_at:
        raise NotFoundError("Prompt not found")
    return entry


# ── List / search ─────────────────────────────────────────────────────────────

@router.get("", response_model=PromptLibraryListResponse)
async def list_prompts(
    q: str | None = Query(None, description="Search title, tags, and prompt content"),
    tag: str | None = Query(None, description="Filter to entries carrying this exact tag"),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PromptLibraryEntry).where(
        PromptLibraryEntry.org_id == token.org_id,
        PromptLibraryEntry.deleted_at.is_(None),
    )
    if tag:
        query = query.where(PromptLibraryEntry.tags.contains([tag]))
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(PromptLibraryEntry.title).like(needle),
                func.lower(PromptLibraryEntry.structured_prompt).like(needle),
                func.lower(cast(PromptLibraryEntry.tags, Text)).like(needle),
            )
        )
    query = query.order_by(PromptLibraryEntry.is_high_performing.desc(), PromptLibraryEntry.updated_at.desc())

    entries = (await db.execute(query)).scalars().all()
    items = await _entries_to_out(db, list(entries))
    return PromptLibraryListResponse(items=items, total=len(items))


# ── Create (admin) ────────────────────────────────────────────────────────────

@router.post("", response_model=PromptLibraryEntryOut, status_code=201)
async def create_prompt(
    body: PromptLibraryCreate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.structured_prompt.strip():
        raise AppValidationError("structured_prompt is required", errors=[])

    entry = PromptLibraryEntry(
        org_id=token.org_id,
        created_by_id=token.user_id,
        title=body.title.strip() or "Untitled prompt",
        tags=[t.strip().lower() for t in body.tags if t.strip()],
        raw_input=body.raw_input,
        structured_prompt=body.structured_prompt,
        current_version=1,
    )
    db.add(entry)
    await db.flush()

    db.add(PromptLibraryVersion(
        entry_id=entry.id,
        version=1,
        structured_prompt=entry.structured_prompt,
        editor_id=token.user_id,
        note="Initial version",
    ))
    await db.commit()
    await db.refresh(entry)
    return await _entry_to_out(db, entry)


# ── Version history ───────────────────────────────────────────────────────────

@router.get("/{entry_id}/history", response_model=list[PromptLibraryVersionOut])
async def get_history(
    entry_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_org_entry(db, entry_id, token.org_id)

    rows = (await db.execute(
        select(PromptLibraryVersion)
        .where(PromptLibraryVersion.entry_id == entry_id)
        .order_by(PromptLibraryVersion.version.desc())
    )).scalars().all()

    editor_ids = {r.editor_id for r in rows if r.editor_id}
    editors_map: dict[UUID, str] = {}
    if editor_ids:
        user_rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(editor_ids)))).all()
        editors_map = {r.id: r.full_name for r in user_rows}

    return [
        PromptLibraryVersionOut(
            version=r.version,
            structured_prompt=r.structured_prompt,
            editor_id=str(r.editor_id) if r.editor_id else None,
            editor_name=editors_map.get(r.editor_id, "Unknown") if r.editor_id else "Unknown",
            note=r.note,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Update / restore / delete (admin) ─────────────────────────────────────────

@router.patch("/{entry_id}", response_model=PromptLibraryEntryOut)
async def update_prompt(
    entry_id: UUID,
    body: PromptLibraryUpdate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_org_entry(db, entry_id, token.org_id)

    if body.title is not None:
        entry.title = body.title.strip() or entry.title
    if body.tags is not None:
        entry.tags = [t.strip().lower() for t in body.tags if t.strip()]

    if body.structured_prompt is not None and body.structured_prompt != entry.structured_prompt:
        if not body.structured_prompt.strip():
            raise AppValidationError("structured_prompt cannot be empty", errors=[])
        entry.structured_prompt = body.structured_prompt
        entry.current_version += 1
        db.add(PromptLibraryVersion(
            entry_id=entry.id,
            version=entry.current_version,
            structured_prompt=entry.structured_prompt,
            editor_id=token.user_id,
            note=body.note,
        ))

    await db.commit()
    await db.refresh(entry)
    return await _entry_to_out(db, entry)


@router.post("/{entry_id}/restore/{version}", response_model=PromptLibraryEntryOut)
async def restore_version(
    entry_id: UUID,
    version: int,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_org_entry(db, entry_id, token.org_id)

    target = await db.scalar(
        select(PromptLibraryVersion).where(
            PromptLibraryVersion.entry_id == entry_id,
            PromptLibraryVersion.version == version,
        )
    )
    if not target:
        raise NotFoundError(f"Version {version} not found")

    entry.structured_prompt = target.structured_prompt
    entry.current_version += 1
    db.add(PromptLibraryVersion(
        entry_id=entry.id,
        version=entry.current_version,
        structured_prompt=entry.structured_prompt,
        editor_id=token.user_id,
        note=f"Restored from v{version}",
    ))
    await db.commit()
    await db.refresh(entry)
    return await _entry_to_out(db, entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_prompt(
    entry_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_org_entry(db, entry_id, token.org_id)
    entry.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Performance flag (any org member — sales manually marks what converted) ──

@router.patch("/{entry_id}/performance", response_model=PromptLibraryEntryOut)
async def mark_performance(
    entry_id: UUID,
    body: MarkPerformingRequest,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_org_entry(db, entry_id, token.org_id)
    entry.is_high_performing = body.is_high_performing
    await db.commit()
    await db.refresh(entry)
    return await _entry_to_out(db, entry)


# ── Sync existing agent prompts into the library (admin) ─────────────────────

@router.post("/sync-from-agents", response_model=SyncFromAgentsResponse)
async def sync_from_agents(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a library entry for every org agent template that doesn't have one
    yet. Covers agents created after the one-time migration backfill (see
    alembic/versions/0022_prompt_library.py) ran, without hooking into agent
    creation itself.
    """
    already_synced = set(
        (await db.execute(
            select(PromptLibraryEntry.source_agent_id).where(
                PromptLibraryEntry.org_id == token.org_id,
                PromptLibraryEntry.source_agent_id.is_not(None),
            )
        )).scalars().all()
    )

    agents = (await db.execute(
        select(AgentTemplate).where(
            AgentTemplate.org_id == token.org_id,
            AgentTemplate.deleted_at.is_(None),
        )
    )).scalars().all()

    created = 0
    for agent in agents:
        if agent.id in already_synced or not agent.system_prompt.strip():
            continue
        entry = PromptLibraryEntry(
            org_id=token.org_id,
            created_by_id=agent.created_by_id,
            source_agent_id=agent.id,
            title=agent.name,
            tags=derive_tags_from_text(agent.name, agent.description),
            structured_prompt=agent.system_prompt,
            current_version=1,
        )
        db.add(entry)
        await db.flush()
        db.add(PromptLibraryVersion(
            entry_id=entry.id,
            version=1,
            structured_prompt=entry.structured_prompt,
            editor_id=agent.created_by_id,
            note="Imported from existing agent",
        ))
        created += 1

    await db.commit()
    return SyncFromAgentsResponse(
        created=created,
        message=f"Added {created} prompt(s) from existing agents" if created else "Library is already up to date",
    )

