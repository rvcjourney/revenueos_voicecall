"""
app/api/inbound_agents.py — Inbound Agents CRUD (admin-only).

Deliberately separate from app/api/agents.py's AgentTemplate CRUD: inbound
agents answer calls arriving on a phone number (assigned via
POST /api/sip-trunks/{trunk_id}/inbound), not campaigns/test-calls, and have
no member access-request workflow -- admins manage them directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, require_admin
from app.core.exceptions import NotFoundError
from app.core.plan_features import check_agent_voice_settings
from app.database import get_db
from app.models.inbound_agent import InboundAgentTemplate
from app.schemas.inbound_agent import (
    InboundAgentCreate,
    InboundAgentListResponse,
    InboundAgentOut,
    InboundAgentUpdate,
)

router = APIRouter()


def _to_out(a: InboundAgentTemplate) -> InboundAgentOut:
    return InboundAgentOut(
        id=str(a.id),
        name=a.name,
        description=a.description,
        language=str(a.language),
        welcome_message=a.welcome_message,
        system_prompt=a.system_prompt,
        voice_id=a.voice_id,
        voice_provider=str(a.voice_provider),
        llm_model=a.llm_model,
        llm_temperature=a.llm_temperature,
        max_call_duration_seconds=a.max_call_duration_seconds,
        created_at=a.created_at,
    )


@router.get("", response_model=InboundAgentListResponse)
async def list_inbound_agents(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(InboundAgentTemplate).where(
        InboundAgentTemplate.org_id == token.org_id,
        InboundAgentTemplate.deleted_at.is_(None),
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(InboundAgentTemplate.created_at.desc()))).scalars().all()
    return InboundAgentListResponse(items=[_to_out(a) for a in rows], total=total)


@router.get("/{agent_id}", response_model=InboundAgentOut)
async def get_inbound_agent(
    agent_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(InboundAgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Inbound agent not found")
    return _to_out(agent)


@router.post("", response_model=InboundAgentOut, status_code=201)
async def create_inbound_agent(
    body: InboundAgentCreate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await check_agent_voice_settings(
        db, token.org_id, voice_provider=body.voice_provider, voice_id=body.voice_id
    )

    agent = InboundAgentTemplate(
        org_id=token.org_id,
        created_by_id=token.user_id,
        **body.model_dump(),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.patch("/{agent_id}", response_model=InboundAgentOut)
async def update_inbound_agent(
    agent_id: UUID,
    body: InboundAgentUpdate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(InboundAgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Inbound agent not found")

    if body.voice_provider is not None or body.voice_id is not None:
        await check_agent_voice_settings(
            db, token.org_id,
            voice_provider=body.voice_provider or agent.voice_provider,
            voice_id=body.voice_id if body.voice_id is not None else agent.voice_id,
        )

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_inbound_agent(
    agent_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(InboundAgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Inbound agent not found")

    agent.deleted_at = datetime.now(timezone.utc)
    await db.commit()
