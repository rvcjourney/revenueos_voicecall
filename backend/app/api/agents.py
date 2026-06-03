from __future__ import annotations

import uuid as _uuid_module
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import NotFoundError, ConflictError, ValidationError as AppValidationError
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.agent_access import AgentAccessRequest
from app.models.call import Call, CallDirection, CallStatus, CallOutcome
from app.models.user import User
from app.schemas.agent import AgentAccessRequestOut, AgentCreate, AgentListResponse, AgentOut, AgentUpdate

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

    # For members, attach the access_status from agent_access_requests
    if token.role == "admin":
        access_map: dict[str, tuple[str, str | None]] = {}  # agent_id → (status, request_id)
    else:
        req_rows = (await db.execute(
            select(AgentAccessRequest).where(
                AgentAccessRequest.user_id == token.user_id,
                AgentAccessRequest.org_id == token.org_id,
            )
        )).scalars().all()
        access_map = {str(r.agent_id): (r.status, str(r.id)) for r in req_rows}

    items = []
    for agent in rows:
        out = _to_out(agent)
        if token.role == "admin":
            out.access_status = "approved"
            out.access_request_id = None
        else:
            status, req_id = access_map.get(str(agent.id), ("locked", None))
            out.access_status = status
            out.access_request_id = req_id
        items.append(out)

    return AgentListResponse(items=items, total=total)


@router.post("/{agent_id}/request-access", status_code=201)
async def request_agent_access(
    agent_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Member requests access to an AI Agent. Admin approves/rejects from admin panel."""
    if token.role == "admin":
        raise AppValidationError("Admins already have full access to all agents", errors=[])

    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent not found")

    existing = await db.scalar(
        select(AgentAccessRequest).where(
            AgentAccessRequest.agent_id == agent_id,
            AgentAccessRequest.user_id == token.user_id,
        )
    )
    if existing:
        if existing.status == "approved":
            raise ConflictError("You already have access to this agent")
        if existing.status == "pending":
            raise ConflictError("Your access request is already pending admin approval")
        # rejected → allow re-requesting
        existing.status = "pending"
        await db.commit()
        return {"message": "Access re-requested. Waiting for admin approval."}

    req = AgentAccessRequest(
        agent_id=agent_id,
        user_id=token.user_id,
        org_id=token.org_id,
        status="pending",
    )
    db.add(req)
    await db.commit()
    return {"message": "Access requested. Waiting for admin approval."}


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate,
    token: TokenPayload = Depends(require_admin),
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
    token: TokenPayload = Depends(require_admin),
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
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")

    agent.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Test call ─────────────────────────────────────────────────────────────────

class TestCallRequest(BaseModel):
    phone_number: str


class TestCallResponse(BaseModel):
    call_id: str
    status: str


@router.post("/{agent_id}/test-call", response_model=TestCallResponse, status_code=202)
async def test_call(
    agent_id: UUID,
    body: TestCallRequest,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Place a real outbound test call using the given agent template.
    Returns immediately with a call_id; poll GET /api/calls/{call_id} for status.
    """
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")

    # Normalise phone number to E.164 (+91 default for India)
    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    # Create a Call record immediately so we can return call_id to the frontend
    room_name = f"test-{_uuid_module.uuid4().hex}"
    call = Call(
        org_id=token.org_id,
        phone_number=phone,
        direction=CallDirection.OUTBOUND,
        status=CallStatus.INITIATED,
        outcome=CallOutcome.PENDING,
        livekit_room_name=room_name,
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Dispatch to Celery worker (calls queue)
    from app.workers.tasks.campaign import place_test_call
    place_test_call.apply_async(
        args=[str(agent_id), phone, str(call.id), str(token.org_id)],
        queue="calls",
    )

    return TestCallResponse(call_id=str(call.id), status="initiated")
