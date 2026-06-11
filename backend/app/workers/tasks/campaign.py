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
from sqlalchemy import func, select, update

from app.config import settings
from app.core.vobiz import fetch_recording_for_call
from app.database import make_worker_session_factory

# NullPool: fresh DB connection per session, no reuse across asyncio.run() calls.
# See make_worker_session_factory() docstring for full explanation.
AsyncSessionLocal = make_worker_session_factory()
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


_LOCK_TTL = 300  # 5 minutes — active dispatchers refresh this on every call via _refresh_lock


# ── Per-trunk concurrent call slot management ─────────────────────────────────

_MAX_CONCURRENT_PER_TRUNK = 3   # max parallel calls per phone number
_SLOT_KEY_TTL = 3600            # 1-hour safety TTL prevents stuck counters after crashes

# Lua: atomically increment only if count < max_concurrent. Returns 1 if acquired, 0 if full.
_LUA_ACQUIRE_SLOT = """
local val = redis.call('GET', KEYS[1])
local cur = tonumber(val) or 0
if cur < tonumber(ARGV[1]) then
    redis.call('INCR', KEYS[1])
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    return 1
end
return 0
"""


def _slot_key(livekit_trunk_id: str) -> str:
    return f"motm:trunk:active:{livekit_trunk_id}"


async def _acquire_trunk_slot(livekit_trunk_id: str) -> bool:
    """Atomically grab one of the 3 allowed concurrent call slots for this trunk.
    Returns True if acquired, False if trunk is at capacity.
    Falls back to True (allow) if Redis is unavailable.
    """
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        result = await r.eval(
            _LUA_ACQUIRE_SLOT, 1,
            _slot_key(livekit_trunk_id),
            _MAX_CONCURRENT_PER_TRUNK,
            _SLOT_KEY_TTL,
        )
        return bool(result)
    except Exception:
        return True  # fail open — don't block calls if Redis is down


async def _release_trunk_slot(livekit_trunk_id: str) -> None:
    """Decrement the trunk's active-call counter. Floors at 0 to guard against bugs."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        count = await r.decr(_slot_key(livekit_trunk_id))
        if count < 0:
            await r.set(_slot_key(livekit_trunk_id), 0)
    except Exception:
        pass  # best-effort


async def _acquire_lock(campaign_id: str) -> bool:
    """True if we grabbed the lock; False if another worker already holds it."""
    try:
        from app.core.redis import get_redis
        return bool(await (await get_redis()).set(_lock_key(campaign_id), "1", nx=True, ex=_LOCK_TTL))
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


async def _refresh_lock(campaign_id: str) -> None:
    try:
        from app.core.redis import get_redis
        await (await get_redis()).expire(_lock_key(campaign_id), _LOCK_TTL)
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

async def _next_pending_batch(session, campaign_id, limit: int) -> list[CampaignContact]:
    """Lock and return up to `limit` PENDING contacts (FIFO by created_at)."""
    result = await session.execute(
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == ContactStatus.PENDING,
        )
        .order_by(CampaignContact.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return result.scalars().all()


async def _next_retry_batch(session, campaign_id, retry_after_minutes: int, limit: int) -> list[CampaignContact]:
    """Return up to `limit` NO_ANSWER contacts past their retry delay."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=retry_after_minutes)
    result = await session.execute(
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == ContactStatus.NO_ANSWER,
            CampaignContact.last_attempted_at <= cutoff,
        )
        .order_by(CampaignContact.last_attempted_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return result.scalars().all()


# ── SIP trunk resolution ───────────────────────────────────────────────────────

async def _resolve_trunk(session, campaign: Campaign) -> tuple[str, str]:
    """Return (livekit_trunk_id, caller_id) using campaign trunk → org default → settings fallback."""
    if campaign.sip_trunk_id:
        trunk = await session.get(SipTrunk, campaign.sip_trunk_id)
        if trunk and trunk.is_active and not trunk.deleted_at:
            return trunk.livekit_trunk_id, trunk.caller_id

    org_default = await session.scalar(
        select(SipTrunk).where(
            SipTrunk.org_id == campaign.org_id,
            SipTrunk.is_default.is_(True),
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
    )
    if org_default:
        return org_default.livekit_trunk_id, org_default.caller_id

    return settings.DEFAULT_SIP_TRUNK_ID, settings.DEFAULT_SIP_CALLER_ID


# ── LiveKit helpers ────────────────────────────────────────────────────────────

async def _place_call(
    http: aiohttp.ClientSession,
    *,
    room_name: str,
    phone: str,
    contact_name: str,
    livekit_trunk_id: str,
    sip_caller_id: str,
    call_id: str,
    campaign_id: str,
    org_id: str,
    agent_template_id: str,
    system_prompt: str = "",
    welcome_message: str = "",
    voice_id: str = "",
    voice_provider: str = "elevenlabs",
    language: str = "hinglish",
    llm_model: str = "",
    llm_temperature: float = 0.7,
) -> str:
    """
    Create room → dispatch AI agent + initiate SIP call (both in parallel).
    Returns "placed", "no_answer", or "failed".
    """
    url, key, secret = settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET
    lk = LiveKitAPI(url, key, secret)
    try:
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
                    "voice_provider": voice_provider,
                    "language": language,
                    "llm_model": llm_model,
                    "llm_temperature": llm_temperature,
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
                        sip_number=sip_caller_id,
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
    finally:
        await lk.aclose()


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

        lk = LiveKitAPI(url, key, secret)
        try:
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
        finally:
            await lk.aclose()

    # Exceeded max duration — force-kill the room
    log.warning("call_timeout_force_close", room=room_name, timeout=timeout_seconds)
    lk = LiveKitAPI(url, key, secret)
    try:
        await lk.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
    except Exception:
        pass
    finally:
        await lk.aclose()
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
        call_outcome = CallOutcome.NO_ANSWER  # phone not picked up
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
        # Call was placed and connected. The agent already POSTed the real outcome
        # via /api/calls/{id}/agent-report before disconnecting — do NOT touch outcome here.
        call_status = CallStatus.COMPLETED
        call_outcome = None  # sentinel: skip outcome update
        contact_status = ContactStatus.COMPLETED

    duration = (
        int((now - call.started_at).total_seconds()) if call.started_at else None
    )

    call_values: dict = dict(status=call_status, ended_at=now, duration_seconds=duration)
    if call_outcome is not None:
        call_values["outcome"] = call_outcome

    await session.execute(
        update(Call)
        .where(Call.id == call.id)
        .values(**call_values)
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


# ── Background recording fetch ────────────────────────────────────────────────

async def _save_recording_async(
    *,
    call_id: uuid.UUID,
    to_number: str,
    called_after: datetime,
    auth_id: str,
    auth_token: str,
    initial_delay: float = 90.0,
    max_attempts: int = 6,
    attempt_interval: float = 30.0,
) -> None:
    """
    Wait for Vobiz to process the recording (~2 min), then save the URL.
    Runs as a fire-and-forget asyncio task so the call loop is not blocked.
    """
    await asyncio.sleep(initial_delay)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        for attempt in range(max_attempts):
            if attempt > 0:
                await asyncio.sleep(attempt_interval)
            try:
                url = await fetch_recording_for_call(
                    http,
                    auth_id=auth_id,
                    auth_token=auth_token,
                    to_number=to_number,
                    called_after=called_after,
                    retries=1,
                    retry_delay=0,
                )
                if url:
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            await session.execute(
                                update(Call).where(Call.id == call_id).values(recording_url=url)
                            )
                    log.info("recording_url_saved", call_id=str(call_id), url=url[:60])
                    return
            except Exception as exc:
                log.warning("recording_save_error", call_id=str(call_id), error=str(exc))
    log.warning("recording_fetch_gave_up", call_id=str(call_id), to=to_number)


# ── Per-call coroutine (runs in parallel inside the dispatch loop) ────────────

async def _run_one_call(
    http: aiohttp.ClientSession,
    *,
    campaign_id: str,
    org_id: uuid.UUID,
    agent_template_id: uuid.UUID,
    call_id: uuid.UUID,
    contact_id: uuid.UUID,
    contact_phone: str,
    contact_name: str,
    room_name: str,
    livekit_trunk_id: str,
    sip_caller_id: str,
    max_duration: int,
    system_prompt: str,
    welcome_message: str,
    voice_id: str,
    voice_provider: str,
    language: str,
    llm_model: str,
    llm_temperature: float,
) -> None:
    """Place one call, wait for it to finish, and finalize — all with its own DB session."""

    # Wait up to 5 minutes for a slot on this trunk (max 3 concurrent calls per phone number)
    slot_acquired = False
    for attempt in range(30):  # 30 × 10 s = 5 min
        if await _acquire_trunk_slot(livekit_trunk_id):
            slot_acquired = True
            break
        if attempt == 0:
            log.info("trunk_at_capacity_waiting",
                     trunk=livekit_trunk_id, phone=contact_phone,
                     max=_MAX_CONCURRENT_PER_TRUNK)
        await asyncio.sleep(10)

    if not slot_acquired:
        # Trunk stayed saturated for 5 min — put contact back so next dispatch cycle retries it.
        log.warning("trunk_slot_timeout_resetting_contact",
                    trunk=livekit_trunk_id, phone=contact_phone)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(CampaignContact)
                    .where(CampaignContact.id == contact_id)
                    .values(status=ContactStatus.PENDING)
                )
                # Remove the pre-created Call record — the call was never actually placed.
                call_row = await session.get(Call, call_id)
                if call_row:
                    await session.delete(call_row)
        return

    try:
        place_result = await _place_call(
            http,
            room_name=room_name,
            phone=contact_phone,
            contact_name=contact_name,
            livekit_trunk_id=livekit_trunk_id,
            sip_caller_id=sip_caller_id,
            call_id=str(call_id),
            campaign_id=campaign_id,
            org_id=str(org_id),
            agent_template_id=str(agent_template_id),
            system_prompt=system_prompt,
            welcome_message=welcome_message,
            voice_id=voice_id,
            voice_provider=voice_provider,
            language=language,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
        )

        if place_result == "placed":
            wait_result = await _wait_for_room_empty(
                http,
                room_name=room_name,
                timeout_seconds=max_duration + 60,
                campaign_id=campaign_id,
            )
        else:
            wait_result = "skipped"

        log.info("call_done", room=room_name, place=place_result, wait=wait_result)

        call_started_at_utc: datetime | None = None
        async with AsyncSessionLocal() as session:
            async with session.begin():
                call_row = await session.get(Call, call_id)
                contact_row = await session.get(CampaignContact, contact_id)
                campaign_row = await session.get(Campaign, uuid.UUID(campaign_id))
                if call_row:
                    call_started_at_utc = call_row.started_at
                await _finalize(
                    session,
                    call=call_row,
                    contact=contact_row,
                    campaign=campaign_row,
                    place_result=place_result,
                    wait_result=wait_result,
                )

        if place_result == "placed" and settings.VOBIZ_AUTH_ID and settings.VOBIZ_AUTH_TOKEN:
            asyncio.create_task(_save_recording_async(
                call_id=call_id,
                to_number=contact_phone,
                called_after=call_started_at_utc or datetime.now(timezone.utc) - timedelta(minutes=30),
                auth_id=settings.VOBIZ_AUTH_ID,
                auth_token=settings.VOBIZ_AUTH_TOKEN,
            ))
    finally:
        await _release_trunk_slot(livekit_trunk_id)


# ── Main dispatcher loop ───────────────────────────────────────────────────────

async def _dispatch_loop(http: aiohttp.ClientSession, campaign_id: str) -> None:
    """
    Parallel-call dispatcher.
    Each iteration picks up to `calls_per_minute` contacts and runs them
    simultaneously with asyncio.gather().  Exits when the campaign is done,
    paused, or outside the calling window.
    """
    while True:
        # ── Re-read campaign at the top of every iteration ─────────────────
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
            await _refresh_lock(campaign_id)  # prevent lock expiry while waiting for window
            await asyncio.sleep(60)
            continue

        concurrency = max(1, campaign.calls_per_minute)
        needs_retry_wait = False
        batch: list[dict] = []           # call kwargs to pass to _run_one_call
        livekit_trunk_id: str = ""
        tmpl_kwargs: dict = {}

        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Pick up to `concurrency` contacts (PENDING first, then retries)
                contacts = await _next_pending_batch(session, campaign.id, concurrency)
                remaining = concurrency - len(contacts)
                if remaining > 0:
                    contacts += await _next_retry_batch(
                        session, campaign.id, campaign.retry_after_minutes, remaining
                    )

                if not contacts:
                    no_answer_waiting = await session.scalar(
                        select(func.count()).where(
                            CampaignContact.campaign_id == campaign.id,
                            CampaignContact.status == ContactStatus.NO_ANSWER,
                        )
                    )
                    if no_answer_waiting:
                        needs_retry_wait = True
                    else:
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

                if not needs_retry_wait:
                    livekit_trunk_id, sip_caller_id = await _resolve_trunk(session, campaign)
                    tmpl = await session.get(AgentTemplate, campaign.agent_template_id)

                    if not livekit_trunk_id:
                        log.error("no_sip_trunk_configured", campaign_id=campaign_id)
                        await session.execute(
                            update(Campaign)
                            .where(Campaign.id == campaign.id)
                            .values(status=CampaignStatus.FAILED)
                        )
                        return

                    tmpl_kwargs = dict(
                        agent_template_id=campaign.agent_template_id,
                        max_duration=tmpl.max_call_duration_seconds if tmpl else 600,
                        system_prompt=(tmpl.system_prompt or "") if tmpl else "",
                        welcome_message=(tmpl.welcome_message or "") if tmpl else "",
                        voice_id=(tmpl.voice_id or "") if tmpl else "",
                        voice_provider=str(tmpl.voice_provider) if tmpl else "elevenlabs",
                        language=str(tmpl.language) if tmpl else "hinglish",
                        llm_model=(tmpl.llm_model or "") if tmpl else "",
                        llm_temperature=tmpl.llm_temperature if tmpl else 0.7,
                    )

                    for contact in contacts:
                        # DNC check
                        if await _is_dnc_blocked(session, campaign.org_id, contact.phone):
                            await session.execute(
                                update(CampaignContact)
                                .where(CampaignContact.id == contact.id)
                                .values(status=ContactStatus.DO_NOT_CALL)
                            )
                            log.info("contact_dnc_blocked", phone=contact.phone)
                            continue

                        room_name = f"camp-{campaign_id[:8]}-{uuid.uuid4().hex[:8]}"

                        await session.execute(
                            update(CampaignContact)
                            .where(CampaignContact.id == contact.id)
                            .values(status=ContactStatus.DIALING)
                        )

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

                        batch.append(dict(
                            call_id=call_obj.id,
                            contact_id=contact.id,
                            contact_phone=contact.phone,
                            contact_name=contact.name,
                            room_name=room_name,
                        ))

        if needs_retry_wait:
            log.info("no_contacts_ready_waiting_for_retry", campaign_id=campaign_id)
            await asyncio.sleep(60)
            continue

        if not batch:
            continue  # all contacts in this batch were DNC-blocked

        log.info("placing_calls", campaign_id=campaign_id, count=len(batch),
                 phones=[d["contact_phone"] for d in batch])

        # ── Run all calls in this batch simultaneously ─────────────────────
        await asyncio.gather(*[
            _run_one_call(
                http,
                campaign_id=campaign_id,
                org_id=campaign.org_id,
                livekit_trunk_id=livekit_trunk_id,
                sip_caller_id=sip_caller_id,
                **tmpl_kwargs,
                **d,
            )
            for d in batch
        ])

        # Loop immediately — pick next batch while previous results are written


async def _reset_stale_dialing(campaign_id: str) -> None:
    """Reset any DIALING contacts to PENDING on dispatcher start (crash recovery)."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                update(CampaignContact)
                .where(
                    CampaignContact.campaign_id == uuid.UUID(campaign_id),
                    CampaignContact.status == ContactStatus.DIALING,
                )
                .values(status=ContactStatus.PENDING)
            )
            if result.rowcount:
                log.warning("reset_stale_dialing_contacts", campaign_id=campaign_id, count=result.rowcount)


async def _run_campaign_async(campaign_id: str) -> None:
    """Outer wrapper: acquire lock, run the loop, release lock."""
    if not await _acquire_lock(campaign_id):
        log.info("campaign_already_running", campaign_id=campaign_id)
        return

    # Reset any contacts stuck in DIALING from a previous crashed run
    await _reset_stale_dialing(campaign_id)

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


# ── Test call ─────────────────────────────────────────────────────────────────

async def _run_test_call_async(
    agent_id: str,
    phone_number: str,
    call_id: str,
    org_id: str,
) -> None:
    """Place a single test call for an agent template (no campaign)."""
    from uuid import UUID as _UUID

    async with AsyncSessionLocal() as session:
        call_row = await session.get(Call, _UUID(call_id))
        agent = await session.get(AgentTemplate, _UUID(agent_id))
        if not agent or not call_row:
            log.error("test_call_missing_records", agent_id=agent_id, call_id=call_id)
            return

        room_name = call_row.livekit_room_name

        _default_trunk = await session.scalar(
            select(SipTrunk).where(
                SipTrunk.org_id == _UUID(org_id),
                SipTrunk.is_default.is_(True),
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )
        livekit_trunk_id = (_default_trunk.livekit_trunk_id if _default_trunk else None) or settings.DEFAULT_SIP_TRUNK_ID
        sip_caller_id    = (_default_trunk.caller_id        if _default_trunk else None) or settings.DEFAULT_SIP_CALLER_ID

        system_prompt   = agent.system_prompt or ""
        welcome_msg     = agent.welcome_message or ""
        voice_id        = agent.voice_id or ""
        voice_provider  = str(agent.voice_provider) if agent.voice_provider else "elevenlabs"
        language        = str(agent.language) if agent.language else "hinglish"
        llm_model       = agent.llm_model or ""
        llm_temperature = float(agent.llm_temperature or 0.7)

    log.info("test_call_start", call_id=call_id, phone=phone_number, room=room_name)

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        place_result = await _place_call(
            http,
            room_name=room_name,
            phone=phone_number,
            contact_name="Test",
            livekit_trunk_id=livekit_trunk_id,
            sip_caller_id=sip_caller_id,
            call_id=call_id,
            campaign_id="",
            org_id=org_id,
            agent_template_id=agent_id,
            system_prompt=system_prompt,
            welcome_message=welcome_msg,
            voice_id=voice_id,
            voice_provider=voice_provider,
            language=language,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
        )

        log.info("test_call_placed", call_id=call_id, result=place_result)

        if place_result == "placed":
            await _wait_for_room_empty(
                http,
                room_name=room_name,
                timeout_seconds=660,
                campaign_id="",  # no campaign lock — refresh is a harmless no-op
            )

    # Finalize the Call row
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        call_row = await session.get(Call, _UUID(call_id))
        if call_row:
            if place_result == "no_answer":
                call_row.status = CallStatus.NO_ANSWER
                call_row.outcome = CallOutcome.NO_ANSWER
            elif place_result == "failed":
                call_row.status = CallStatus.FAILED
            else:
                # Agent will POST the real outcome via /calls/{id}/agent-report
                call_row.status = CallStatus.COMPLETED
            call_row.ended_at = now
            if call_row.started_at:
                call_row.duration_seconds = int((now - call_row.started_at).total_seconds())
            await session.commit()

    log.info("test_call_done", call_id=call_id, result=place_result)


@celery_app.task(
    name="app.workers.tasks.campaign.place_test_call",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def place_test_call(self, agent_id: str, phone_number: str, call_id: str, org_id: str) -> None:
    """Place a single test call for an agent template (no campaign)."""
    asyncio.run(_run_test_call_async(agent_id, phone_number, call_id, org_id))


@celery_app.task(name="app.workers.tasks.campaign.launch_scheduled_campaigns", bind=True)
def launch_scheduled_campaigns(self) -> None:
    """Beat task (every 60 s): auto-launch SCHEDULED campaigns whose start_time has passed."""
    asyncio.run(_launch_scheduled_async())


async def _launch_scheduled_async() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Campaign.id, Campaign.name).where(
                Campaign.status == CampaignStatus.SCHEDULED,
                Campaign.start_time <= now,
                Campaign.deleted_at.is_(None),
            )
        )
        scheduled = [(str(r[0]), r[1]) for r in rows]

    if not scheduled:
        return

    log.info("launching_scheduled_campaigns", count=len(scheduled))
    for cid, cname in scheduled:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                campaign = await session.get(Campaign, uuid.UUID(cid))
                if campaign and campaign.status == CampaignStatus.SCHEDULED:
                    campaign.status = CampaignStatus.RUNNING
                    campaign.started_at = now
        run_campaign.delay(cid)
        log.info("scheduled_campaign_launched", campaign_id=cid, name=cname)


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
            select(Campaign.id, Campaign.name).where(
                Campaign.status == CampaignStatus.RUNNING,
                Campaign.deleted_at.is_(None),
            )
        )
        running = [(str(r[0]), r[1]) for r in rows]

    if not running:
        return

    log.info("resume_check", running_campaigns=len(running))

    for cid, cname in running:
        has_lock = bool(await redis.exists(_lock_key(cid)))
        if has_lock:
            log.debug("campaign_dispatcher_alive", campaign_id=cid, name=cname)
            continue  # dispatcher is alive

        async with AsyncSessionLocal() as session:
            campaign = await session.get(Campaign, uuid.UUID(cid))

        if not campaign:
            continue

        in_window = _in_calling_window(campaign)
        log.info(
            "stalled_campaign_found",
            campaign_id=cid,
            name=cname,
            in_window=in_window,
            tz=campaign.timezone,
            window=f"{campaign.calling_window_start}–{campaign.calling_window_end}",
            days=campaign.calling_days,
        )

        if in_window:
            run_campaign.delay(cid)
            log.info("stalled_campaign_requeued", campaign_id=cid, name=cname)
        else:
            log.info("stalled_campaign_outside_window", campaign_id=cid, name=cname)
