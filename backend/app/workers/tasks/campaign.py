"""
app/workers/tasks/campaign.py — Sequential campaign call dispatcher.

DESIGN: one call at a time per campaign.
  1. Pick the next PENDING contact.
  2. DNC-check it.
  3. Place the call (LiveKit room → agent dispatch → SIP participant).
  4. Block until the LiveKit room has zero participants (SIP party + AI agent both gone).
  5. Record the outcome, then go back to step 1.

Multiple campaigns run in parallel across Celery workers, but within a
single campaign calls are strictly sequential — the next dial never starts
until the previous room is confirmed empty.

Retry contacts (NO_ANSWER within retry budget) are processed on a second
pass after all fresh PENDING contacts are exhausted.

Window exit: when the current time falls outside the campaign's calling window
the task exits cleanly. The beat task `resume_stalled_campaigns` re-queues
it when the window opens again.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import structlog
from livekit import api as lk_api
from livekit.api import LiveKitAPI
from livekit.api.twirp_client import TwirpError
from sqlalchemy import select, update

from app.config import settings
from app.core.vobiz import fetch_recording_for_call
from app.database import AsyncSessionLocal
from app.models.agent import AgentTemplate
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, ContactStatus
from app.models.call import Call, CallDirection, CallOutcome, CallStatus
from app.models.dnc import DoNotCallEntry, SystemDncEntry
from app.models.sip import SipTrunk
from app.workers.celery_app import celery_app

log = structlog.get_logger(__name__)

# SIP response codes that mean "not answered" (not a system fault)
_SIP_NO_ANSWER_CODES = {"486", "480", "408", "600", "603"}

# Day-name → Python weekday integer (Monday = 0)
_DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# ── Redis lock (with in-memory fallback for local dev without Redis) ───────────

_mem_locks: set[str] = set()


def _lock_key(campaign_id: str) -> str:
    return f"motm:dispatcher:lock:{campaign_id}"


async def _acquire_lock(campaign_id: str, ttl: int = 3600) -> bool:
    """True if we grabbed the lock; False if another worker already holds it."""
    try:
        from app.core.redis import get_redis
        return bool(await (await get_redis()).set(_lock_key(campaign_id), "1", nx=True, ex=ttl))
    except Exception:
        if campaign_id in _mem_locks:
            return False
        _mem_locks.add(campaign_id)
        return True


async def _release_lock(campaign_id: str) -> None:
    try:
        from app.core.redis import get_redis
        await (await get_redis()).delete(_lock_key(campaign_id))
    except Exception:
        _mem_locks.discard(campaign_id)


async def _refresh_lock(campaign_id: str, ttl: int = 3600) -> None:
    try:
        from app.core.redis import get_redis
        await (await get_redis()).expire(_lock_key(campaign_id), ttl)
    except Exception:
        pass  # in-memory lock doesn't expire


# ── Calling-window check ───────────────────────────────────────────────────────

def _in_calling_window(campaign: Campaign) -> bool:
    """True if right now is within the campaign's allowed day/time window."""
    try:
        tz = ZoneInfo(campaign.timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Kolkata")

    now = datetime.now(tz)
    allowed_days = {_DAY_MAP[d] for d in campaign.calling_days if d in _DAY_MAP}
    if now.weekday() not in allowed_days:
        return False
    # now.time() strips tzinfo — matches the naive time values stored in DB
    current = now.time().replace(tzinfo=None)
    return campaign.calling_window_start <= current <= campaign.calling_window_end


# ── DNC check ─────────────────────────────────────────────────────────────────

async def _is_dnc_blocked(session, org_id, phone: str) -> bool:
    """True if phone is on the system-wide or org-level DNC list."""
    if await session.scalar(
        select(SystemDncEntry.id).where(SystemDncEntry.phone_number == phone)
    ):
        return True
    return bool(await session.scalar(
        select(DoNotCallEntry.id).where(
            DoNotCallEntry.org_id == org_id,
            DoNotCallEntry.phone_number == phone,
        )
    ))


# ── Contact queue ──────────────────────────────────────────────────────────────

async def _next_pending(session, campaign_id) -> CampaignContact | None:
    """Lock and return one PENDING contact (FIFO by created_at)."""
    result = await session.execute(
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == ContactStatus.PENDING,
        )
        .order_by(CampaignContact.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


async def _next_retry(session, campaign_id, retry_after_minutes: int) -> CampaignContact | None:
    """Return a NO_ANSWER contact that is past its retry delay, or None."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=retry_after_minutes)
    result = await session.execute(
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == ContactStatus.NO_ANSWER,
            CampaignContact.last_attempted_at <= cutoff,
        )
        .order_by(CampaignContact.last_attempted_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalar_one_or_none()


# ── SIP trunk resolution ───────────────────────────────────────────────────────

async def _resolve_livekit_trunk_id(session, campaign: Campaign) -> str:
    """Campaign trunk → org default trunk → settings fallback."""
    if campaign.sip_trunk_id:
        trunk = await session.get(SipTrunk, campaign.sip_trunk_id)
        if trunk and trunk.is_active:
            return trunk.livekit_trunk_id

    org_default = await session.scalar(
        select(SipTrunk.livekit_trunk_id).where(
            SipTrunk.org_id == campaign.org_id,
            SipTrunk.is_default.is_(True),
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
    )
    return org_default or settings.DEFAULT_SIP_TRUNK_ID


# ── LiveKit helpers ────────────────────────────────────────────────────────────

async def _place_call(
    http: aiohttp.ClientSession,
    *,
    room_name: str,
    phone: str,
    contact_name: str,
    livekit_trunk_id: str,
    call_id: str,
    campaign_id: str,
    org_id: str,
    agent_template_id: str,
    system_prompt: str = "",
    welcome_message: str = "",
    voice_id: str = "",
    llm_model: str = "",
) -> str:
    """
    Create room → dispatch AI agent + initiate SIP call (both in parallel).
    Returns "placed", "no_answer", or "failed".
    """
    url, key, secret = settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET

    async with LiveKitAPI(url, key, secret) as lk:
        await lk.room.create_room(
            lk_api.CreateRoomRequest(
                name=room_name,
                metadata=json.dumps({
                    "call_id": call_id,
                    "campaign_id": campaign_id,
                    "org_id": org_id,
                    "agent_template_id": agent_template_id,
                    "contact_name": contact_name,
                    "system_prompt": system_prompt,
                    "welcome_message": welcome_message,
                    "voice_id": voice_id,
                    "llm_model": llm_model,
                }),
            )
        )

        try:
            await asyncio.gather(
                lk.agent_dispatch.create_dispatch(
                    lk_api.CreateAgentDispatchRequest(
                        agent_name="voice-call-agent",
                        room=room_name,
                        metadata=json.dumps({"agent_template_id": agent_template_id}),
                    )
                ),
                lk.sip.create_sip_participant(
                    lk_api.CreateSIPParticipantRequest(
                        sip_trunk_id=livekit_trunk_id,
                        sip_call_to=phone,
                        sip_number=settings.DEFAULT_SIP_CALLER_ID,
                        room_name=room_name,
                        participant_identity=f"phone-{phone.replace('+', '')}",
                        participant_name=contact_name,
                        play_ringtone=True,
                        wait_until_answered=True,
                    )
                ),
            )
            return "placed"

        except TwirpError as exc:
            sip_code = str(exc.metadata.get("sip_status_code", ""))
            outcome = "no_answer" if sip_code in _SIP_NO_ANSWER_CODES else "failed"
            log.warning("sip_call_not_placed", room=room_name, sip_code=sip_code, outcome=outcome)
            try:
                await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            return outcome


async def _wait_for_room_empty(
    http: aiohttp.ClientSession,
    *,
    room_name: str,
    timeout_seconds: int,
    campaign_id: str,
    poll_interval: int = 5,
) -> str:
    """
    Poll LiveKit every `poll_interval` seconds.
    Returns "done" when the room has zero participants (SIP caller and AI agent
    have both disconnected), or "timeout" if the call exceeded `timeout_seconds`.
    """
    url, key, secret = settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        await _refresh_lock(campaign_id)  # prevent lock from expiring during long calls

        try:
            async with LiveKitAPI(url, key, secret) as lk:
                resp = await lk.room.list_participants(
                    lk_api.ListParticipantsRequest(room=room_name)
                )
            if len(resp.participants) == 0:
                log.info("room_empty_call_done", room=room_name)
                return "done"
        except TwirpError:
            # Room no longer exists — call definitely ended
            log.info("room_gone_call_done", room=room_name)
            return "done"
        except Exception as exc:
            log.warning("room_poll_error", room=room_name, error=str(exc))

    # Exceeded max duration — force-kill the room
    log.warning("call_timeout_force_close", room=room_name, timeout=timeout_seconds)
    try:
        async with LiveKitAPI(url, key, secret) as lk:
            await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception:
        pass
    return "timeout"


# ── Post-call finalization ─────────────────────────────────────────────────────

async def _finalize(
    session,
    *,
    call: Call,
    contact: CampaignContact,
    campaign: Campaign,
    place_result: str,
    wait_result: str,
) -> None:
    """
    Write final Call status, CampaignContact status, and Campaign aggregate
    counters. All counter increments are atomic SQL — never read-modify-write.
    """
    now = datetime.now(timezone.utc)

    if place_result == "no_answer":
        call_status = CallStatus.NO_ANSWER
        call_outcome = CallOutcome.PENDING  # agent never connected, nothing to classify
        contact_status = (
            ContactStatus.NO_ANSWER
            if (contact.attempt_count + 1) < campaign.max_retries
            else ContactStatus.FAILED
        )
    elif place_result == "failed":
        call_status = CallStatus.FAILED
        call_outcome = CallOutcome.PENDING
        contact_status = ContactStatus.FAILED
    else:
        # Call was placed and connected. The agent will POST the real outcome
        # via /api/calls/{id}/agent-report within ~15s of the call ending.
        # Set PENDING now; it will be overwritten by the agent callback.
        call_status = CallStatus.COMPLETED
        call_outcome = CallOutcome.PENDING
        contact_status = ContactStatus.COMPLETED

    duration = (
        int((now - call.started_at).total_seconds()) if call.started_at else None
    )

    await session.execute(
        update(Call)
        .where(Call.id == call.id)
        .values(status=call_status, outcome=call_outcome, ended_at=now, duration_seconds=duration)
    )

    await session.execute(
        update(CampaignContact)
        .where(CampaignContact.id == contact.id)
        .values(
            status=contact_status,
            attempt_count=CampaignContact.attempt_count + 1,
            last_attempted_at=now,
        )
    )

    # Atomic counter increments — safe under concurrent campaign updates
    await session.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id)
        .values(completed_calls=Campaign.completed_calls + 1)
    )
    if contact_status == ContactStatus.FAILED:
        await session.execute(
            update(Campaign)
            .where(Campaign.id == campaign.id)
            .values(failed_count=Campaign.failed_count + 1)
        )


# ── Main dispatcher loop ───────────────────────────────────────────────────────

async def _dispatch_loop(http: aiohttp.ClientSession, campaign_id: str) -> None:
    """
    Infinite loop: pick a contact → call it → wait for it to finish → repeat.
    Exits when the campaign is done, paused, or the calling window closes.
    """
    while True:
        # ── Re-read campaign status at the top of every iteration ──────────
        async with AsyncSessionLocal() as session:
            campaign = await session.get(Campaign, uuid.UUID(campaign_id))

        if not campaign:
            log.error("campaign_not_found", campaign_id=campaign_id)
            return
        if campaign.status != CampaignStatus.RUNNING:
            log.info("campaign_not_running", campaign_id=campaign_id, status=campaign.status)
            return
        if not _in_calling_window(campaign):
            log.info("outside_calling_window_waiting", campaign_id=campaign_id)
            await asyncio.sleep(60)  # re-check every minute until window opens
            continue

        # ── Pick next contact + resolve trunk (one transaction) ────────────
        room_name = f"camp-{campaign_id[:8]}-{uuid.uuid4().hex[:8]}"
        call_id: uuid.UUID | None = None
        contact_phone: str = ""
        contact_name: str = ""
        contact_id: uuid.UUID | None = None
        livekit_trunk_id: str = ""
        max_duration: int = 600

        async with AsyncSessionLocal() as session:
            async with session.begin():
                contact = await _next_pending(session, campaign.id)
                if contact is None:
                    contact = await _next_retry(session, campaign.id, campaign.retry_after_minutes)

                if contact is None:
                    # All contacts exhausted — campaign is done
                    await session.execute(
                        update(Campaign)
                        .where(Campaign.id == campaign.id)
                        .values(
                            status=CampaignStatus.COMPLETED,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    log.info("campaign_completed", campaign_id=campaign_id)
                    return

                # DNC check — done inside the transaction so the status update
                # is committed atomically with the DIALING mark below.
                if await _is_dnc_blocked(session, campaign.org_id, contact.phone):
                    await session.execute(
                        update(CampaignContact)
                        .where(CampaignContact.id == contact.id)
                        .values(status=ContactStatus.DO_NOT_CALL)
                    )
                    log.info("contact_dnc_blocked", phone=contact.phone)
                    # session.begin() commits on exit even via continue
                    continue

                # Mark DIALING to prevent another worker picking the same contact
                await session.execute(
                    update(CampaignContact)
                    .where(CampaignContact.id == contact.id)
                    .values(status=ContactStatus.DIALING)
                )

                # Create the Call record before touching LiveKit
                call_obj = Call(
                    org_id=campaign.org_id,
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    livekit_room_name=room_name,
                    phone_number=contact.phone,
                    direction=CallDirection.OUTBOUND,
                    status=CallStatus.INITIATED,
                    started_at=datetime.now(timezone.utc),
                )
                session.add(call_obj)
                await session.flush()

                # Capture all values we need after the session closes
                call_id = call_obj.id
                contact_id = contact.id
                contact_phone = contact.phone
                contact_name = contact.name

                # Resolve SIP trunk and template inside the same session
                livekit_trunk_id = await _resolve_livekit_trunk_id(session, campaign)
                tmpl = await session.get(AgentTemplate, campaign.agent_template_id)
                max_duration = tmpl.max_call_duration_seconds if tmpl else 600
                tmpl_system_prompt = tmpl.system_prompt if tmpl else ""
                tmpl_welcome_message = tmpl.welcome_message if tmpl else ""
                tmpl_voice_id = tmpl.voice_id if tmpl else ""
                tmpl_llm_model = tmpl.llm_model if tmpl else ""

        if not livekit_trunk_id:
            log.error("no_sip_trunk_configured", campaign_id=campaign_id)
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await session.execute(
                        update(Campaign)
                        .where(Campaign.id == campaign.id)
                        .values(status=CampaignStatus.FAILED)
                    )
            return

        log.info("placing_call", room=room_name, phone=contact_phone, contact_id=str(contact_id))

        # ── Place the call ─────────────────────────────────────────────────
        # The SIP call setup can take several seconds; no DB session is held.
        place_result = await _place_call(
            http,
            room_name=room_name,
            phone=contact_phone,
            contact_name=contact_name,
            livekit_trunk_id=livekit_trunk_id,
            call_id=str(call_id),
            campaign_id=str(campaign.id),
            org_id=str(campaign.org_id),
            agent_template_id=str(campaign.agent_template_id),
            system_prompt=tmpl_system_prompt,
            welcome_message=tmpl_welcome_message,
            voice_id=tmpl_voice_id,
            llm_model=tmpl_llm_model,
        )

        # ── Wait for the call to end before dialling the next contact ──────
        if place_result == "placed":
            wait_result = await _wait_for_room_empty(
                http,
                room_name=room_name,
                # Extra 60 s grace beyond max duration for TTS/hangup to complete
                timeout_seconds=max_duration + 60,
                campaign_id=campaign_id,
            )
        else:
            wait_result = "skipped"

        log.info("call_done", room=room_name, place=place_result, wait=wait_result)

        # ── Record outcome ─────────────────────────────────────────────────
        call_started_at_utc: datetime | None = None
        async with AsyncSessionLocal() as session:
            async with session.begin():
                call_row = await session.get(Call, call_id)
                contact_row = await session.get(CampaignContact, contact_id)
                campaign_row = await session.get(Campaign, campaign.id)
                call_started_at_utc = call_row.started_at if call_row else None
                await _finalize(
                    session,
                    call=call_row,
                    contact=contact_row,
                    campaign=campaign_row,
                    place_result=place_result,
                    wait_result=wait_result,
                )

        # ── Fetch recording URL from Vobiz (best-effort, non-blocking) ────────
        if place_result == "placed" and settings.VOBIZ_AUTH_ID and settings.VOBIZ_AUTH_TOKEN:
            try:
                recording_url = await fetch_recording_for_call(
                    http,
                    auth_id=settings.VOBIZ_AUTH_ID,
                    auth_token=settings.VOBIZ_AUTH_TOKEN,
                    to_number=contact_phone,
                    called_after=call_started_at_utc or datetime.now(timezone.utc) - timedelta(minutes=30),
                )
                if recording_url:
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            await session.execute(
                                update(Call)
                                .where(Call.id == call_id)
                                .values(recording_url=recording_url)
                            )
                    log.info("recording_url_saved", call_id=str(call_id), url=recording_url[:60])
            except Exception as exc:
                log.warning("recording_fetch_failed", call_id=str(call_id), error=str(exc))

        # Loop: next contact starts immediately after previous room is empty


async def _run_campaign_async(campaign_id: str) -> None:
    """Outer wrapper: acquire lock, run the loop, release lock."""
    if not await _acquire_lock(campaign_id):
        log.info("campaign_already_running", campaign_id=campaign_id)
        return

    log.info("campaign_dispatcher_start", campaign_id=campaign_id)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
            await _dispatch_loop(http, campaign_id)
    except Exception:
        log.exception("campaign_dispatcher_error", campaign_id=campaign_id)
    finally:
        await _release_lock(campaign_id)
        log.info("campaign_dispatcher_exit", campaign_id=campaign_id)


# ── Celery task entry points ───────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.tasks.campaign.run_campaign",
    bind=True,
    max_retries=0,       # beat handles re-queuing, not Celery auto-retry
    acks_late=True,
)
def run_campaign(self, campaign_id: str) -> None:
    """
    Launch the sequential dispatcher for one campaign.
    Called by the campaign-start API endpoint and by `resume_stalled_campaigns`.
    """
    asyncio.run(_run_campaign_async(campaign_id))


@celery_app.task(name="app.workers.tasks.campaign.resume_stalled_campaigns", bind=True)
def resume_stalled_campaigns(self) -> None:
    """
    Beat task (every 60 s): re-queue any RUNNING campaign whose dispatcher
    has exited (lock released). Handles calling-window resumption and crash recovery.
    """
    asyncio.run(_resume_stalled_async())


async def _resume_stalled_async() -> None:
    from app.core.redis import get_redis
    redis = await get_redis()

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Campaign.id).where(
                Campaign.status == CampaignStatus.RUNNING,
                Campaign.deleted_at.is_(None),
            )
        )
        campaign_ids = [str(r[0]) for r in rows]

    for cid in campaign_ids:
        if await redis.exists(_lock_key(cid)):
            continue  # dispatcher is alive

        async with AsyncSessionLocal() as session:
            campaign = await session.get(Campaign, uuid.UUID(cid))

        if campaign and _in_calling_window(campaign):
            run_campaign.delay(cid)
            log.info("stalled_campaign_requeued", campaign_id=cid)
