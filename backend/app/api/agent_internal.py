"""
app/api/agent_internal.py — Internal endpoints called only by the LiveKit
agent process (agent/agent.py), never by tenant users or the frontend.

Verified with the HMAC helpers in app/core/security.py (sign_webhook_payload /
verify_webhook_signature) -- previously written but never wired up anywhere.
This is the first thing to actually use them: unlike /api/calls/{id}/agent-report
(which only acts on a call_id that already exists), this endpoint can create
real Call rows and read prompt content from just a trunk id, so it shouldn't
be left unauthenticated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.concurrency import acquire_org_slot, release_org_slot, resolve_org_max_concurrent
from app.core.credits import has_credits_remaining
from app.core.deps import require_agent_webhook_signature
from app.core.exceptions import ConflictError, QuotaExceededError
from app.database import get_db
from app.models.call import Call, CallDirection, CallOutcome, CallStatus
from app.models.inbound_agent import InboundAgentTemplate
from app.models.sip import SipTrunk

router = APIRouter()


class InboundStartRequest(BaseModel):
    sip_trunk_id: UUID
    room_name: str
    from_number: str
    to_number: str


class InboundStartResponse(BaseModel):
    call_id: str
    system_prompt: str
    welcome_message: str
    voice_provider: str
    voice_id: str
    language: str
    llm_model: str
    llm_temperature: float
    max_call_duration_seconds: int


@router.post("/inbound/start", response_model=InboundStartResponse, dependencies=[Depends(require_agent_webhook_signature)])
async def start_inbound_call(
    body: InboundStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the agent as soon as an inbound SIP participant joins. Resolves
    which InboundAgentTemplate answers this number, creates the Call row (no
    row exists yet for inbound calls, unlike outbound where the API layer
    pre-creates one before dialing), and returns the same config shape the
    agent already builds from room metadata for outbound calls.
    """
    trunk = await db.get(SipTrunk, body.sip_trunk_id)
    if not trunk or trunk.deleted_at or not trunk.inbound_enabled or not trunk.inbound_agent_template_id:
        raise HTTPException(status_code=404, detail="Inbound calling is not set up for this number")

    agent = await db.get(InboundAgentTemplate, trunk.inbound_agent_template_id)
    if not agent or agent.deleted_at:
        raise HTTPException(status_code=404, detail="Inbound agent not found")

    # Mirror the same two gates outbound calls go through before dialing
    # (app/api/agents.py:test_call, app/api/campaigns.py:launch_campaign) --
    # inbound previously had neither, so an org could take unlimited inbound
    # calls for free with no cap. A non-200 here makes the agent process treat
    # this call as unresolvable and hang up (see _resolve_inbound_call in
    # agent/agent.py), the same as e.g. inbound calling not being configured.
    if not await has_credits_remaining(db, trunk.org_id):
        raise QuotaExceededError(
            "Organization has used all its available call credits this period."
        )

    org_max_concurrent = await resolve_org_max_concurrent(db, trunk.org_id)
    if not await acquire_org_slot(trunk.org_id, org_max_concurrent):
        raise ConflictError("Organization is at its concurrent-call capacity.")

    call = Call(
        id=uuid7(),
        org_id=trunk.org_id,
        campaign_id=None,
        sip_trunk_id=trunk.id,
        livekit_room_name=body.room_name,
        phone_number=body.from_number,
        direction=CallDirection.INBOUND,
        status=CallStatus.CONNECTED,
        outcome=CallOutcome.PENDING,
        started_at=datetime.now(timezone.utc),
        answered_at=datetime.now(timezone.utc),
    )
    db.add(call)
    try:
        await db.commit()
    except Exception:
        # The org slot acquired above is only ever released from the other end
        # of the call's life (app/api/calls.py:agent_report) -- if we never
        # actually created the Call row, that release will never happen, so
        # release it here to avoid leaking a permanently-stuck slot.
        await release_org_slot(trunk.org_id)
        raise
    await db.refresh(call)

    return InboundStartResponse(
        call_id=str(call.id),
        system_prompt=agent.system_prompt,
        welcome_message=agent.welcome_message,
        voice_provider=str(agent.voice_provider),
        voice_id=agent.voice_id,
        language=str(agent.language),
        llm_model=agent.llm_model,
        llm_temperature=agent.llm_temperature,
        max_call_duration_seconds=agent.max_call_duration_seconds,
    )
