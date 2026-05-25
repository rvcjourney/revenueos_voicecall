from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.agent import AgentTemplate
from app.schemas.agent import AgentCreate, AgentListResponse, AgentOut, AgentUpdate

router = APIRouter()


# ── Prompt optimizer ──────────────────────────────────────────────────────────

class PromptOptimizeRequest(BaseModel):
    raw_input: str   # raw company knowledge + sales goal from the sales team


class PromptOptimizeResponse(BaseModel):
    optimized_prompt: str


@router.post("/optimize-prompt", response_model=PromptOptimizeResponse)
async def optimize_prompt(
    body: PromptOptimizeRequest,
    token: TokenPayload = Depends(get_current_user),
):
    """
    Use Groq LLM to transform raw company knowledge into a
    structured, optimized voice agent system prompt.
    """
    if not body.raw_input or len(body.raw_input.strip()) < 20:
        raise HTTPException(status_code=422, detail="raw_input is too short — provide meaningful company knowledge")

    try:
        from app.services.prompt_optimizer import optimize_prompt as _optimize
        result = await _optimize(body.raw_input)
        return PromptOptimizeResponse(optimized_prompt=result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prompt generation failed: {e}")


def _to_out(a: AgentTemplate) -> AgentOut:
    return AgentOut(
        id=str(a.id),
        name=a.name,
        description=a.description,
        language=a.language,
        welcome_message=a.welcome_message,
        system_prompt=a.system_prompt,
        voice_id=a.voice_id,
        voice_provider=a.voice_provider,
        llm_model=a.llm_model,
        llm_temperature=a.llm_temperature,
        max_call_duration_seconds=a.max_call_duration_seconds,
        created_at=a.created_at,
    )


@router.get("", response_model=AgentListResponse)
async def list_agents(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentTemplate).where(
        AgentTemplate.org_id == token.org_id,
        AgentTemplate.deleted_at.is_(None),
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(AgentTemplate.created_at.desc()))).scalars().all()
    return AgentListResponse(items=[_to_out(r) for r in rows], total=total)


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = AgentTemplate(
        org_id=token.org_id,
        created_by_id=token.user_id,
        **body.model_dump(),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")
    return _to_out(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    return _to_out(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")

    from datetime import datetime, timezone
    agent.deleted_at = datetime.now(timezone.utc)
    await db.commit()
