from __future__ import annotations

import logging
import uuid as _uuid_module
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

log = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import NotFoundError, ConflictError, ValidationError as AppValidationError, PermissionDeniedError, QuotaExceededError
from app.core.plan_features import check_agent_voice_settings
from app.config import settings
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.agent_access import AgentAccessRequest
from app.models.agent_creation_request import AgentCreationRequest
from app.models.call import Call, CallDirection, CallStatus, CallOutcome
from app.schemas.agent import AgentCreate, AgentCreationRequestOut, AgentListResponse, AgentOut, AgentUpdate

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
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Prompt optimizer service unavailable — try again later")
    except Exception:
        log.exception("optimize_prompt_error")
        raise HTTPException(status_code=500, detail="Prompt generation failed — please try again")


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
        access_map = {str(r.agent_id): (r.status, str(r.id), r.can_edit) for r in req_rows}

    items = []
    for agent in rows:
        out = _to_out(agent)
        if token.role == "admin":
            out.access_status = "approved"
            out.access_request_id = None
            out.can_edit = True
        else:
            status, req_id, can_edit = access_map.get(str(agent.id), ("locked", None, False))
            out.access_status = status
            out.access_request_id = req_id
            out.can_edit = can_edit
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


@router.post("/creation-request", status_code=201)
async def request_agent_creation(
    agent_name: str = Form(...),
    company_name: str = Form(...),
    product_service: str = Form(...),
    target_customers: str = Form(...),
    key_points: str = Form(...),
    file: UploadFile | None = File(None),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Member requests a new AI Agent by submitting company info + optional file."""
    file_key: str | None = None
    file_name: str | None = None

    if file and file.filename:
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:
            raise AppValidationError("File must be under 10MB", errors=[])
        key = f"agent-requests/{token.org_id}/{_uuid_module.uuid4().hex}/{file.filename}"
        from app.storage.backend import get_storage
        storage = get_storage()
        await storage.upload(
            settings.BUCKET_EXPORTS,
            key,
            contents,
            content_type=file.content_type or "application/octet-stream",
        )
        file_key = key
        file_name = file.filename

    creation_req = AgentCreationRequest(
        org_id=token.org_id,
        user_id=token.user_id,
        agent_name=agent_name.strip(),
        company_name=company_name.strip(),
        product_service=product_service.strip(),
        target_customers=target_customers.strip(),
        key_points=key_points.strip(),
        file_key=file_key,
        file_name=file_name,
        status="pending",
    )
    db.add(creation_req)
    await db.commit()
    await db.refresh(creation_req)
    return {"id": str(creation_req.id), "message": "Request submitted. Admin will create your agent soon."}


@router.get("/my-creation-requests", response_model=list[AgentCreationRequestOut])
async def my_creation_requests(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Member sees their own submitted creation requests."""
    rows = (await db.execute(
        select(AgentCreationRequest)
        .where(AgentCreationRequest.user_id == token.user_id)
        .order_by(AgentCreationRequest.created_at.desc())
    )).scalars().all()
    return [
        AgentCreationRequestOut(
            id=str(r.id),
            agent_name=r.agent_name,
            company_name=r.company_name,
            status=r.status,
            admin_notes=r.admin_notes,
            has_file=bool(r.file_key),
            file_name=r.file_name,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await check_agent_voice_settings(
        db, token.org_id, voice_provider=body.voice_provider, voice_id=body.voice_id
    )

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

    # Admins can always edit. Members need an approved access with can_edit=True.
    if token.role != "admin":
        access = await db.scalar(
            select(AgentAccessRequest).where(
                AgentAccessRequest.agent_id == agent_id,
                AgentAccessRequest.user_id == token.user_id,
                AgentAccessRequest.status == "approved",
                AgentAccessRequest.can_edit.is_(True),
            )
        )
        if not access:
            raise PermissionDeniedError("You do not have edit permission for this agent")

    if body.voice_provider is not None or body.voice_id is not None:
        await check_agent_voice_settings(
            db,
            token.org_id,
            voice_provider=body.voice_provider or agent.voice_provider,
            voice_id=body.voice_id if body.voice_id is not None else agent.voice_id,
        )

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    out = _to_out(agent)
    out.access_status = "approved"
    out.can_edit = True  # caller passed the permission check above (or is admin)
    return out


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
    trunk_id: str | None = None


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

    # Members need approved+can_edit access to run test calls
    if token.role != "admin":
        access = await db.scalar(
            select(AgentAccessRequest).where(
                AgentAccessRequest.agent_id == agent_id,
                AgentAccessRequest.user_id == token.user_id,
                AgentAccessRequest.status == "approved",
                AgentAccessRequest.can_edit.is_(True),
            )
        )
        if not access:
            raise PermissionDeniedError("You do not have permission to test call this agent")

    # Normalise phone number to E.164 (+91 default for India)
    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    # Validate the chosen "From" trunk belongs to this org (and, for
    # non-admins, is actually assigned to them) before handing it to the
    # worker — otherwise a stale/foreign trunk_id would silently fall back
    # to is_default inside _run_test_call_async.
    trunk_id: str | None = None
    if body.trunk_id:
        from app.models.sip import SipTrunk, UserSipTrunk

        trunk_query = select(SipTrunk).where(
            SipTrunk.id == UUID(body.trunk_id),
            SipTrunk.org_id == token.org_id,
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
        if token.role != "admin":
            trunk_query = trunk_query.join(UserSipTrunk, UserSipTrunk.trunk_id == SipTrunk.id).where(
                UserSipTrunk.user_id == token.user_id
            )
        trunk = await db.scalar(trunk_query)
        if not trunk:
            raise NotFoundError("Selected phone number not found")
        trunk_id = str(trunk.id)

    from app.core.credits import has_credits_remaining

    if not await has_credits_remaining(db, token.org_id):
        raise QuotaExceededError(
            "Your organization has used all its available call credits. Visit Billing to add more before placing calls."
        )

    # One call in flight per admin/user, platform-wide (test calls + campaign
    # calls share this cap) — reject outright rather than queueing, since this
    # is a synchronous request the caller is waiting on.
    from app.core.concurrency import acquire_user_slot

    if not await acquire_user_slot(token.user_id):
        raise ConflictError("You already have a call in progress — wait for it to finish before starting another")

    try:
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

        # Dispatch to Celery worker (calls queue) — the worker releases this
        # user's slot once the call actually ends (see _run_test_call_async).
        from app.workers.tasks.campaign import place_test_call
        place_test_call.apply_async(
            args=[str(agent_id), phone, str(call.id), str(token.org_id), trunk_id, str(token.user_id)],
            queue="calls",
        )
    except Exception:
        # Never dispatched (or never will be worked) -- release now instead of
        # leaving the admin locked out of test calls for up to an hour.
        from app.core.concurrency import release_user_slot

        await release_user_slot(token.user_id)
        raise

    return TestCallResponse(call_id=str(call.id), status="initiated")


# ── Try Now (free demo call) ────────────────────────────────────────────────

class TryNowRequest(BaseModel):
    phone_number: str


@router.post("/try-now", response_model=TestCallResponse, status_code=202)
async def try_now(
    body: TryNowRequest,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Free demo call showcasing QuickHowl itself (app/core/demo_call.py's fixed
    persona) on the platform's own default number — no org/agent lookup, no
    credit charge. Deliberately a separate, simpler pipeline from test_call:
    see app/workers/tasks/campaign.py:place_demo_call.
    """
    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    # Same "one call in flight per admin, platform-wide" cap test calls use —
    # still reasonable here even with no credit cost, since it's the same
    # underlying LiveKit/Vobiz capacity being spent.
    from app.core.concurrency import acquire_user_slot

    if not await acquire_user_slot(token.user_id):
        raise ConflictError("You already have a call in progress — wait for it to finish before starting another")

    try:
        room_name = f"demo-{_uuid_module.uuid4().hex}"
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

        from app.workers.tasks.campaign import place_demo_call
        place_demo_call.apply_async(
            args=[phone, str(call.id), str(token.org_id), str(token.user_id)],
            queue="calls",
        )
    except Exception:
        from app.core.concurrency import release_user_slot

        await release_user_slot(token.user_id)
        raise

    return TestCallResponse(call_id=str(call.id), status="initiated")
