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

from app.core.deps import require_agent_webhook_signature
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
    await db.commit()
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
