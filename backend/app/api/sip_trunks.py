"""
app/api/sip_trunks.py — Phone number (SIP trunk) management.

Admin endpoints  (require role=admin):
  GET    /api/sip-trunks                       — list all trunks in org
  POST   /api/sip-trunks                       — add a new trunk
  PUT    /api/sip-trunks/{trunk_id}            — update trunk details
  DELETE /api/sip-trunks/{trunk_id}            — soft-delete trunk
  POST   /api/sip-trunks/{trunk_id}/assign     — assign trunk to a user
  DELETE /api/sip-trunks/{trunk_id}/assign/{user_id} — remove assignment
  GET    /api/sip-trunks/{trunk_id}/assignments — list users assigned to trunk
  POST   /api/sip-trunks/connect-vobiz         — self-serve: validate a Vobiz
                                                   DID and provision a LiveKit
                                                   outbound trunk for it
  POST   /api/sip-trunks/{trunk_id}/test       — place a short test call;
                                                   flips is_active on success
  POST   /api/sip-trunks/{trunk_id}/inbound    — set up inbound calling for
                                                   this number (fully automated:
                                                   Vobiz inbound trunk + number
                                                   assign, LiveKit inbound trunk
                                                   + dispatch rule)
  PATCH  /api/sip-trunks/{trunk_id}/inbound    — change which InboundAgentTemplate
                                                   answers this number
  DELETE /api/sip-trunks/{trunk_id}/inbound    — tear down inbound calling

User endpoint (any authenticated user):
  GET    /api/sip-trunks/my                    — list trunks assigned to me
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import UUID

import aiohttp
import structlog
from fastapi import APIRouter, Depends, HTTPException
from livekit import api as lk_api
from livekit.api import LiveKitAPI
from livekit.api.sip_service import SIPTransport as LKSIPTransport
from livekit.api.twirp_client import TwirpError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.config import settings
from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.security import sign_vobiz_webhook_token
from app.core.vobiz import (
    VobizValidationError,
    assign_vobiz_number_to_trunk,
    create_vobiz_inbound_trunk,
    create_vobiz_outbound_trunk,
    delete_vobiz_trunk,
    unassign_vobiz_number,
    validate_vobiz_account_and_did,
)
from app.database import get_db
from app.models.inbound_agent import InboundAgentTemplate
from app.models.sip import SipTrunk, SipTransport, UserSipTrunk
from app.models.user import User

log = structlog.get_logger(__name__)

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TrunkCreate(BaseModel):
    name: str
    livekit_trunk_id: str
    sip_domain: str
    sip_username: str
    sip_password: str
    caller_id: str          # E.164, e.g. "+918888888888"
    transport: str = "tcp"
    is_default: bool = False


class TrunkUpdate(BaseModel):
    name: str | None = None
    caller_id: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class TrunkOut(BaseModel):
    id: str
    name: str
    livekit_trunk_id: str
    sip_domain: str
    sip_username: str
    caller_id: str
    transport: str
    is_default: bool
    is_active: bool
    created_at: datetime
    inbound_enabled: bool
    inbound_agent_template_id: str | None = None
    hangup_webhook_url: str | None = None


class InboundSetupBody(BaseModel):
    inbound_agent_template_id: UUID


class InboundOut(BaseModel):
    trunk_id: str
    inbound_enabled: bool
    inbound_agent_template_id: str | None


class AssignBody(BaseModel):
    user_id: UUID


class ConnectVobizBody(BaseModel):
    auth_id: str
    auth_token: str
    did: str   # E.164, e.g. "+912212345678"


class ConnectVobizResponse(BaseModel):
    trunk_id: str
    status: str
    did: str


class TestTrunkResponse(BaseModel):
    trunk_id: str
    is_active: bool
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_out(trunk: SipTrunk) -> TrunkOut:
    hangup_webhook_url = None
    if settings.PUBLIC_BASE_URL:
        token = sign_vobiz_webhook_token(trunk.id)
        # Vobiz's hangup callback isn't registered automatically anywhere in
        # this codebase (unlike the recording webhook — see connect_vobiz
        # below) — it's set once per Vobiz account/DID directly in Vobiz's
        # own dashboard. This is shown here so whoever configures it there
        # can copy the exact per-trunk-scoped URL instead of the old
        # unscoped one.
        hangup_webhook_url = f"{settings.PUBLIC_BASE_URL}/webhooks/vobiz/hangup?tid={trunk.id}&wt={token}"

    return TrunkOut(
        id=str(trunk.id),
        name=trunk.name,
        livekit_trunk_id=trunk.livekit_trunk_id,
        sip_domain=trunk.sip_domain,
        sip_username=trunk.sip_username,
        caller_id=trunk.caller_id,
        transport=str(trunk.transport),
        is_default=trunk.is_default,
        is_active=trunk.is_active,
        created_at=trunk.created_at,
        inbound_enabled=trunk.inbound_enabled,
        inbound_agent_template_id=str(trunk.inbound_agent_template_id) if trunk.inbound_agent_template_id else None,
        hangup_webhook_url=hangup_webhook_url,
    )


async def _get_trunk(db: AsyncSession, trunk_id: UUID, org_id: UUID) -> SipTrunk:
    trunk = await db.get(SipTrunk, trunk_id)
    if not trunk or trunk.org_id != org_id or trunk.deleted_at:
        raise NotFoundError("Phone number not found")
    return trunk


async def _rebalance_default(db: AsyncSession, org_id: UUID) -> None:
    """
    Keep is_default meaningful after an is_active change: it must never point
    at a trunk that isn't active. Call this whenever a trunk's is_active
    flips (test pass/fail, manual deactivate, delete) unless the caller is
    already setting is_default explicitly in the same request.
    """
    active = (await db.execute(
        select(SipTrunk).where(
            SipTrunk.org_id == org_id,
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
    )).scalars().all()

    current_defaults = (await db.execute(
        select(SipTrunk).where(
            SipTrunk.org_id == org_id,
            SipTrunk.is_default.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
    )).scalars().all()

    if len(active) == 1:
        # The one working number in the org is the obvious default.
        for t in current_defaults:
            if t.id != active[0].id:
                t.is_default = False
        active[0].is_default = True
        return

    # Zero or multiple active trunks: don't guess which one should be
    # default, but never leave "default" pointing at a dead trunk — a
    # stale default is worse than none (it silently triggers the global
    # fallback caller ID instead of surfacing a "no number" error).
    active_ids = {t.id for t in active}
    for t in current_defaults:
        if t.id not in active_ids:
            t.is_default = False


# ── Admin: list all trunks ────────────────────────────────────────────────────

@router.get("", response_model=list[TrunkOut])
async def list_trunks(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SipTrunk)
        .where(SipTrunk.org_id == token.org_id, SipTrunk.deleted_at.is_(None))
        .order_by(SipTrunk.created_at)
    )).scalars().all()
    return [_to_out(r) for r in rows]


# ── Admin: create trunk ───────────────────────────────────────────────────────

@router.post("", response_model=TrunkOut, status_code=201)
async def create_trunk(
    body: TrunkCreate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.transport not in ("tcp", "udp", "tls"):
        raise AppValidationError("transport must be tcp, udp, or tls", errors=[])

    caller_id = body.caller_id.strip().replace(" ", "")
    if not caller_id.startswith("+"):
        caller_id = "+91" + caller_id.lstrip("0")

    # If this trunk is marked default, clear any existing default first
    if body.is_default:
        await db.execute(
            select(SipTrunk)
            .where(SipTrunk.org_id == token.org_id, SipTrunk.is_default.is_(True))
        )
        existing_defaults = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_default.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
        for t in existing_defaults:
            t.is_default = False

    transport_enum = SipTransport(body.transport)
    trunk = SipTrunk(
        org_id=token.org_id,
        name=body.name.strip(),
        livekit_trunk_id=body.livekit_trunk_id.strip(),
        sip_domain=body.sip_domain.strip(),
        sip_username=body.sip_username.strip(),
        sip_password=body.sip_password,
        caller_id=caller_id,
        transport=transport_enum,
        is_default=body.is_default,
        is_active=True,
    )
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)
    return _to_out(trunk)


# ── Admin: self-serve Vobiz connect ───────────────────────────────────────────

@router.post("/connect-vobiz", response_model=ConnectVobizResponse, status_code=201)
async def connect_vobiz(
    body: ConnectVobizBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Self-serve trunk provisioning: validate the org's own Vobiz credentials +
    DID ownership, create a dedicated outbound trunk on the org's own Vobiz
    account (recording + our recording webhook pre-enabled automatically — no
    manual Vobiz console step required from the admin), create a matching
    LiveKit outbound SIP trunk pointed at it, and store it inactive
    (is_active=false) until POST /{trunk_id}/test confirms it works.
    """
    did = body.did.strip().replace(" ", "")
    if not did.startswith("+"):
        did = "+91" + did.lstrip("0")

    # 1. Validate Vobiz credentials + DID ownership before creating anything
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            await validate_vobiz_account_and_did(
                http, auth_id=body.auth_id, auth_token=body.auth_token, did=did,
            )
    except VobizValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not settings.PUBLIC_BASE_URL:
        raise HTTPException(status_code=503, detail="PUBLIC_BASE_URL is not configured on this server")

    # Generated up front (not left to SipTrunk's default) so it can be embedded
    # in the webhook_url below *before* the trunk row exists — Vobiz needs the
    # final URL at trunk-creation time, and the token in it is what lets
    # app/api/webhooks.py verify a recording callback actually belongs to this
    # trunk/org instead of matching by phone number alone across every org.
    trunk_id = uuid7()
    webhook_token = sign_vobiz_webhook_token(trunk_id)

    # 2. Create a dedicated outbound trunk on the org's own Vobiz account, with
    #    recording + the recording webhook pre-enabled in the same request.
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            vobiz_sip_domain = await create_vobiz_outbound_trunk(
                http,
                auth_id=body.auth_id,
                auth_token=body.auth_token,
                did=did,
                webhook_url=f"{settings.PUBLIC_BASE_URL}/webhooks/vobiz/recording?tid={trunk_id}&wt={webhook_token}",
            )
    except VobizValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 3. Create the LiveKit outbound SIP trunk for this DID, pointed at the
    #    org's own new Vobiz trunk domain (not a shared platform-wide one)
    lk = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        trunk_info = await lk.sip.create_outbound_trunk(
            lk_api.CreateSIPOutboundTrunkRequest(
                trunk=lk_api.SIPOutboundTrunkInfo(
                    name=f"vobiz-{did}",
                    address=vobiz_sip_domain,
                    numbers=[did],
                    auth_username=body.auth_id,
                    auth_password=body.auth_token,
                    transport=LKSIPTransport.SIP_TRANSPORT_TCP,
                )
            )
        )
    except TwirpError as exc:
        raise HTTPException(status_code=400, detail=f"Could not create LiveKit SIP trunk: {exc.message}")
    finally:
        await lk.aclose()

    # 4. Store the trunk — inactive until /test succeeds. Vobiz's auth_id/token
    #    doubles as the SIP auth passed to LiveKit above (Vobiz's SIP registration
    #    and its REST API appear to share one credential pair); vobiz_auth_id/
    #    vobiz_auth_token are stored explicitly too so future Vobiz API calls
    #    (e.g. re-validating the DID, recording lookups) don't need to reuse
    #    the sip_* fields.
    # is_default is NOT set here — it's only ever assigned once a trunk
    # passes /test and _rebalance_default confirms it's the org's sole
    # working number. Defaulting an untested trunk is exactly how a
    # campaign ends up trying to call through a number that doesn't work.
    trunk = SipTrunk(
        id=trunk_id,
        org_id=token.org_id,
        name=f"Vobiz {did}",
        livekit_trunk_id=trunk_info.sip_trunk_id,
        sip_domain=vobiz_sip_domain,
        sip_username=body.auth_id,
        sip_password=body.auth_token,
        caller_id=did,
        transport=SipTransport.TCP,
        is_default=False,
        is_active=False,
    )
    trunk.vobiz_auth_id = body.auth_id
    trunk.vobiz_auth_token = body.auth_token
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)

    return ConnectVobizResponse(trunk_id=str(trunk.id), status="pending_test", did=did)


# ── Admin: test a trunk ───────────────────────────────────────────────────────

@router.post("/{trunk_id}/test", response_model=TestTrunkResponse)
async def test_trunk(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Place a short test call on this trunk (dials the trunk's own DID) to
    confirm the LiveKit/Vobiz configuration actually works end to end.
    Sets is_active=true on success; leaves it false and returns the error
    on failure.
    """
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    room_name = f"trunk-test-{trunk.id.hex}-{int(time.time())}"
    lk = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    try:
        try:
            await lk.room.create_room(lk_api.CreateRoomRequest(name=room_name))
            await lk.sip.create_sip_participant(
                lk_api.CreateSIPParticipantRequest(
                    sip_trunk_id=trunk.livekit_trunk_id,
                    sip_call_to=trunk.caller_id,
                    sip_number=trunk.caller_id,
                    room_name=room_name,
                    participant_identity="trunk-test",
                    participant_name="Trunk Test Call",
                    play_ringtone=False,
                    wait_until_answered=False,
                )
            )
        except TwirpError as exc:
            trunk.is_active = False
            await _rebalance_default(db, trunk.org_id)
            await db.commit()
            raise HTTPException(status_code=400, detail=f"Test call failed: {exc.message}")
        except Exception as exc:
            trunk.is_active = False
            await _rebalance_default(db, trunk.org_id)
            await db.commit()
            raise HTTPException(status_code=400, detail=f"Test call failed: {exc}")
        finally:
            try:
                await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
    finally:
        await lk.aclose()

    trunk.is_active = True
    await _rebalance_default(db, trunk.org_id)
    await db.commit()
    await db.refresh(trunk)
    return TestTrunkResponse(
        trunk_id=str(trunk.id),
        is_active=trunk.is_active,
        message="Test call placed successfully",
    )


# ── Admin: set up inbound calling ─────────────────────────────────────────────

async def _get_inbound_agent(db: AsyncSession, agent_id: UUID, org_id: UUID) -> InboundAgentTemplate:
    agent = await db.get(InboundAgentTemplate, agent_id)
    if not agent or agent.org_id != org_id or agent.deleted_at:
        raise NotFoundError("Inbound agent not found")
    return agent


@router.post("/{trunk_id}/inbound", response_model=InboundOut, status_code=201)
async def setup_inbound(
    trunk_id: UUID,
    body: InboundSetupBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Fully automated inbound setup: create a Vobiz inbound trunk pointed at this
    platform's LiveKit SIP endpoint, assign the org's DID to it, create a
    matching LiveKit inbound trunk + dispatch rule (naming the same
    "voice-call-agent" worker used for outbound). No Vobiz console or LiveKit
    dashboard steps required.
    """
    trunk = await _get_trunk(db, trunk_id, token.org_id)
    await _get_inbound_agent(db, body.inbound_agent_template_id, token.org_id)

    if trunk.inbound_enabled:
        raise ConflictError("Inbound calling is already set up for this number — use PATCH to change the agent")
    if not trunk.vobiz_auth_id or not trunk.vobiz_auth_token:
        raise HTTPException(status_code=503, detail="This number has no Vobiz credentials on file")
    if not settings.LIVEKIT_SIP_HOSTNAME:
        raise HTTPException(status_code=503, detail="LIVEKIT_SIP_HOSTNAME is not configured on this server")

    vobiz_auth_id = trunk.vobiz_auth_id
    vobiz_auth_token = trunk.vobiz_auth_token
    did = trunk.caller_id

    # 1. Vobiz: create the inbound trunk, then assign this DID to it.
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            vobiz_inbound_trunk_id = await create_vobiz_inbound_trunk(
                http,
                auth_id=vobiz_auth_id,
                auth_token=vobiz_auth_token,
                did=did,
                inbound_destination=settings.LIVEKIT_SIP_HOSTNAME,
            )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            await assign_vobiz_number_to_trunk(
                http, auth_id=vobiz_auth_id, auth_token=vobiz_auth_token, did=did, trunk_id=vobiz_inbound_trunk_id,
            )
    except VobizValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. LiveKit: create the inbound trunk (scoped to this DID) + a dispatch
    #    rule naming the existing agent worker. Room metadata is deliberately
    #    minimal (just enough to look the call up) -- the agent fetches the
    #    live system_prompt/voice config at call time via
    #    POST /api/internal/inbound/start, the same way outbound always
    #    builds it fresh from the DB rather than caching it anywhere.
    lk = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    livekit_inbound_trunk_id = None
    try:
        try:
            inbound_trunk_info = await lk.sip.create_inbound_trunk(
                lk_api.CreateSIPInboundTrunkRequest(
                    trunk=lk_api.SIPInboundTrunkInfo(
                        name=f"vobiz-inbound-{did}",
                        # LiveKit matches this list against the exact digit string
                        # Vobiz sends in the INVITE's destination number, and Vobiz
                        # doesn't guarantee which of "+91XXXXXXXXXX" / "91XXXXXXXXXX"
                        # it uses -- registering both formats is the documented way
                        # to cover that ambiguity (confirmed with Vobiz support after
                        # a real inbound call 404'd on a trunk that only had the "+"
                        # form registered).
                        numbers=[did, did.lstrip("+")],
                    )
                )
            )
            livekit_inbound_trunk_id = inbound_trunk_info.sip_trunk_id

            dispatch_rule_info = await lk.sip.create_dispatch_rule(
                lk_api.CreateSIPDispatchRuleRequest(
                    trunk_ids=[livekit_inbound_trunk_id],
                    name=f"inbound-{did}",
                    rule=lk_api.SIPDispatchRule(
                        dispatch_rule_individual=lk_api.SIPDispatchRuleIndividual(room_prefix=f"inbound-{did.lstrip('+')}-")
                    ),
                    room_config=lk_api.RoomConfiguration(
                        metadata=json.dumps({"call_type": "inbound", "sip_trunk_id": str(trunk.id)}),
                        agents=[lk_api.RoomAgentDispatch(agent_name=settings.LIVEKIT_AGENT_NAME)],
                    ),
                )
            )
        except TwirpError as exc:
            # Persist whatever succeeded so DELETE /inbound can clean it up later
            # instead of leaving an orphaned, untracked Vobiz/LiveKit resource.
            trunk.vobiz_inbound_trunk_id = vobiz_inbound_trunk_id
            trunk.livekit_inbound_trunk_id = livekit_inbound_trunk_id
            await db.commit()
            log.warning("inbound_setup_livekit_failed", trunk_id=str(trunk.id), error=exc.message)
            raise HTTPException(status_code=400, detail=f"Could not set up LiveKit inbound routing: {exc.message}")
    finally:
        await lk.aclose()

    trunk.vobiz_inbound_trunk_id = vobiz_inbound_trunk_id
    trunk.livekit_inbound_trunk_id = livekit_inbound_trunk_id
    trunk.livekit_inbound_dispatch_rule_id = dispatch_rule_info.sip_dispatch_rule_id
    trunk.inbound_agent_template_id = body.inbound_agent_template_id
    trunk.inbound_enabled = True
    await db.commit()
    await db.refresh(trunk)

    return InboundOut(
        trunk_id=str(trunk.id),
        inbound_enabled=trunk.inbound_enabled,
        inbound_agent_template_id=str(trunk.inbound_agent_template_id),
    )


@router.patch("/{trunk_id}/inbound", response_model=InboundOut)
async def update_inbound_agent(
    trunk_id: UUID,
    body: InboundSetupBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Swap which InboundAgentTemplate answers this number. No Vobiz/LiveKit
    calls needed -- the agent config is always fetched live at call time."""
    trunk = await _get_trunk(db, trunk_id, token.org_id)
    if not trunk.inbound_enabled:
        raise HTTPException(status_code=400, detail="Inbound calling isn't set up for this number yet")
    await _get_inbound_agent(db, body.inbound_agent_template_id, token.org_id)

    trunk.inbound_agent_template_id = body.inbound_agent_template_id
    await db.commit()
    await db.refresh(trunk)
    return InboundOut(
        trunk_id=str(trunk.id),
        inbound_enabled=trunk.inbound_enabled,
        inbound_agent_template_id=str(trunk.inbound_agent_template_id),
    )


@router.delete("/{trunk_id}/inbound", response_model=InboundOut)
async def teardown_inbound(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Tear down inbound calling for this number. Best-effort on the Vobiz/
    LiveKit side (logs failures rather than blocking) -- the local DB state
    always ends up cleared so the admin can retry setup cleanly."""
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    if trunk.vobiz_auth_id and trunk.vobiz_auth_token:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
                await unassign_vobiz_number(
                    http, auth_id=trunk.vobiz_auth_id, auth_token=trunk.vobiz_auth_token, did=trunk.caller_id,
                )
        except Exception as exc:
            log.warning("inbound_teardown_vobiz_failed", trunk_id=str(trunk.id), error=str(exc))

        # Actually delete the Vobiz-side inbound trunk (verified endpoint --
        # see delete_vobiz_trunk's docstring). unassign_vobiz_number alone
        # was leaving this trunk enabled with the DID still attached, so a
        # later re-setup created a second trunk that never got the number.
        if trunk.vobiz_inbound_trunk_id:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
                    await delete_vobiz_trunk(
                        http, auth_id=trunk.vobiz_auth_id, auth_token=trunk.vobiz_auth_token,
                        trunk_id=trunk.vobiz_inbound_trunk_id,
                    )
            except Exception as exc:
                log.warning("inbound_teardown_vobiz_trunk_delete_failed", trunk_id=str(trunk.id), error=str(exc))

    if trunk.livekit_inbound_dispatch_rule_id or trunk.livekit_inbound_trunk_id:
        lk = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        try:
            if trunk.livekit_inbound_dispatch_rule_id:
                try:
                    await lk.sip.delete_dispatch_rule(
                        lk_api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=trunk.livekit_inbound_dispatch_rule_id)
                    )
                except Exception as exc:
                    log.warning("inbound_teardown_dispatch_rule_failed", trunk_id=str(trunk.id), error=str(exc))
            if trunk.livekit_inbound_trunk_id:
                try:
                    await lk.sip.delete_trunk(
                        lk_api.DeleteSIPTrunkRequest(sip_trunk_id=trunk.livekit_inbound_trunk_id)
                    )
                except Exception as exc:
                    log.warning("inbound_teardown_trunk_failed", trunk_id=str(trunk.id), error=str(exc))
        finally:
            await lk.aclose()

    trunk.inbound_enabled = False
    trunk.inbound_agent_template_id = None
    trunk.vobiz_inbound_trunk_id = None
    trunk.livekit_inbound_trunk_id = None
    trunk.livekit_inbound_dispatch_rule_id = None
    await db.commit()

    return InboundOut(trunk_id=str(trunk.id), inbound_enabled=False, inbound_agent_template_id=None)


# ── Admin: update trunk ───────────────────────────────────────────────────────

@router.put("/{trunk_id}", response_model=TrunkOut)
async def update_trunk(
    trunk_id: UUID,
    body: TrunkUpdate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    if body.name is not None:
        trunk.name = body.name.strip()

    if body.caller_id is not None:
        caller_id = body.caller_id.strip().replace(" ", "")
        if not caller_id.startswith("+"):
            caller_id = "+91" + caller_id.lstrip("0")
        trunk.caller_id = caller_id

    if body.is_active is not None:
        trunk.is_active = body.is_active

    if body.is_default is not None and body.is_default:
        # Explicit admin choice — clear existing org default before setting
        # new one. Takes priority over auto-rebalancing below.
        existing_defaults = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_default.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
        for t in existing_defaults:
            t.is_default = False
        trunk.is_default = True
    elif body.is_default is not None:
        trunk.is_default = False
    elif body.is_active is not None:
        # is_active changed but the caller didn't touch is_default explicitly
        # — make sure "default" doesn't end up pointing at a trunk that was
        # just deactivated.
        await _rebalance_default(db, token.org_id)

    await db.commit()
    await db.refresh(trunk)
    return _to_out(trunk)


# ── Admin: delete trunk ───────────────────────────────────────────────────────

@router.delete("/{trunk_id}", status_code=204)
async def delete_trunk(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)
    trunk.deleted_at = datetime.now(timezone.utc)
    trunk.is_default = False
    trunk.is_active = False
    await _rebalance_default(db, token.org_id)
    await db.commit()


# ── Admin: assign trunk to user ───────────────────────────────────────────────

@router.post("/{trunk_id}/assign", status_code=201)
async def assign_trunk_to_user(
    trunk_id: UUID,
    body: AssignBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    # Verify target user exists in same org
    user = await db.get(User, body.user_id)
    if not user or user.org_id != token.org_id or user.deleted_at:
        raise NotFoundError("User not found")

    # Check not already assigned
    existing = await db.scalar(
        select(UserSipTrunk).where(
            UserSipTrunk.user_id == body.user_id,
            UserSipTrunk.trunk_id == trunk_id,
        )
    )
    if existing:
        raise ConflictError("This phone number is already assigned to that user")

    assignment = UserSipTrunk(
        user_id=body.user_id,
        trunk_id=trunk.id,
        assigned_by_id=token.user_id,
    )
    db.add(assignment)
    await db.commit()
    return {
        "message": f"Phone number '{trunk.name}' assigned to {user.full_name}",
        "trunk_id": str(trunk.id),
        "user_id": str(user.id),
    }


# ── Admin: remove trunk assignment ───────────────────────────────────────────

@router.delete("/{trunk_id}/assign/{user_id}", status_code=204)
async def remove_trunk_assignment(
    trunk_id: UUID,
    user_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_trunk(db, trunk_id, token.org_id)  # verify trunk belongs to org

    assignment = await db.scalar(
        select(UserSipTrunk).where(
            UserSipTrunk.trunk_id == trunk_id,
            UserSipTrunk.user_id == user_id,
        )
    )
    if not assignment:
        raise NotFoundError("Assignment not found")

    await db.delete(assignment)
    await db.commit()


# ── Admin: list users assigned to a trunk ────────────────────────────────────

@router.get("/{trunk_id}/assignments")
async def list_trunk_assignments(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_trunk(db, trunk_id, token.org_id)

    rows = (await db.execute(
        select(UserSipTrunk, User)
        .join(User, UserSipTrunk.user_id == User.id)
        .where(UserSipTrunk.trunk_id == trunk_id)
        .order_by(UserSipTrunk.created_at)
    )).all()

    return [
        {
            "user_id": str(assignment.user_id),
            "full_name": user.full_name,
            "email": user.email,
            "assigned_at": assignment.created_at.isoformat(),
        }
        for assignment, user in rows
    ]


# ── Any user: live call-slot capacity per trunk ───────────────────────────────

@router.get("/capacity")
async def get_trunk_capacity(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return how many of the 3 available call slots each trunk is currently using."""
    MAX_PER_TRUNK = 3

    if token.role == "admin":
        trunks = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
    else:
        trunks = (await db.execute(
            select(SipTrunk)
            .join(UserSipTrunk, UserSipTrunk.trunk_id == SipTrunk.id)
            .where(
                UserSipTrunk.user_id == token.user_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()

    try:
        from app.core.redis import get_redis
        r = await get_redis()
    except Exception:
        r = None

    result = []
    for trunk in trunks:
        active = 0
        if r:
            try:
                val = await r.get(f"motm:trunk:active:{trunk.livekit_trunk_id}")
                active = max(0, int(val or 0))
            except Exception:
                pass
        result.append({
            "trunk_id": str(trunk.id),
            "caller_id": trunk.caller_id,
            "active_calls": active,
            "max_concurrent": MAX_PER_TRUNK,
            "available_slots": max(0, MAX_PER_TRUNK - active),
        })
    return result


# ── Admin: initialize default trunk from env vars ────────────────────────────

@router.post("/init-default", response_model=TrunkOut, status_code=200)
async def init_default_trunk(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed all configured SIP trunks for this org. Idempotent — skips existing ones."""
    trunks_cfg = [
        (settings.DEFAULT_SIP_TRUNK_ID, settings.DEFAULT_SIP_CALLER_ID, "Vobiz SIP Trunk", True),
    ]
    if settings.DEFAULT_SIP_TRUNK_ID_2 and settings.DEFAULT_SIP_CALLER_ID_2:
        trunks_cfg.append(
            (settings.DEFAULT_SIP_TRUNK_ID_2, settings.DEFAULT_SIP_CALLER_ID_2, "Vobiz SIP Trunk 2", False)
        )

    first_trunk = None
    for livekit_id, caller_id, name, is_default in trunks_cfg:
        existing = await db.scalar(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.livekit_trunk_id == livekit_id,
                SipTrunk.deleted_at.is_(None),
            )
        )
        if existing:
            if first_trunk is None:
                first_trunk = existing
            continue

        trunk = SipTrunk(
            org_id=token.org_id,
            name=name,
            livekit_trunk_id=livekit_id,
            sip_domain=settings.VOBIZ_SIP_DOMAIN,
            sip_username=settings.VOBIZ_USERNAME,
            sip_password=settings.VOBIZ_PASSWORD,
            caller_id=caller_id,
            transport=SipTransport.TCP,
            is_default=is_default,
            is_active=True,
        )
        db.add(trunk)
        await db.flush()
        if first_trunk is None:
            first_trunk = trunk

    await db.commit()
    if first_trunk:
        await db.refresh(first_trunk)
    return _to_out(first_trunk)


# ── User: list my assigned trunks ─────────────────────────────────────────────

@router.get("/my", response_model=list[TrunkOut])
async def list_my_trunks(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the phone numbers (SIP trunks) assigned to the current user by admin."""
    # Admins see all active trunks in the org
    if token.role == "admin":
        rows = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            ).order_by(SipTrunk.is_default.desc(), SipTrunk.created_at)
        )).scalars().all()
        return [_to_out(r) for r in rows]

    rows = (await db.execute(
        select(SipTrunk)
        .join(UserSipTrunk, UserSipTrunk.trunk_id == SipTrunk.id)
        .where(
            UserSipTrunk.user_id == token.user_id,
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
        .order_by(SipTrunk.is_default.desc(), SipTrunk.created_at)
    )).scalars().all()
    return [_to_out(r) for r in rows]
