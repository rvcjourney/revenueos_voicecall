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
import random
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
from app.core.concurrency import (
    acquire_org_slot,
    acquire_user_slot,
    decr_queued,
    decr_user_queued,
    incr_queued,
    incr_user_queued,
    release_org_slot,
    release_user_slot,
    resolve_org_max_concurrent,
)
from app.core.credits import has_credits_remaining, record_call_credits
from app.core.vobiz import fetch_recording_for_call, resolve_vobiz_credentials
from app.database import make_worker_session_factory

# NullPool: fresh DB connection per session, no reuse across asyncio.run() calls.
# See make_worker_session_factory() docstring for full explanation.
AsyncSessionLocal = make_worker_session_factory()
from app.models.agent import AgentTemplate
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, ContactStatus
from app.models.call import Call, CallDirection, CallEvent, CallOutcome, CallStatus
from app.models.dnc import DoNotCallEntry, SystemDncEntry
from app.models.sip import SipTrunk
from app.models.user import Organization
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
# The org-level equivalent (plan-based max_concurrent_calls) lives in
# app/core/concurrency.py — shared with the read-only usage API. A call must
# acquire BOTH an org slot and a trunk slot before it's dialed.

_MAX_CONCURRENT_PER_TRUNK = 5   # max parallel calls per phone number (5 per trunk × 2 trunks = 10 total)
_SLOT_KEY_TTL = 3600            # 1-hour safety TTL prevents stuck counters after crashes

# Seconds between org-slot retries while a contact is queued waiting for
# capacity (queue-then-reject — see _run_one_call below).
_ORG_MAX_WAIT_POLL_INTERVAL = 10

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
    except Exception as exc:
        log.error("trunk_slot_redis_fail_open", trunk_id=livekit_trunk_id, error=str(exc))
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


# ── Global CPS (Calls Per Second) rate limiter ────────────────────────────────

_CPS_LIMIT = 1       # max new calls started per second (matches Vobiz plan)
_CPS_KEY = "motm:cps:window"

# Atomically increment a 1-second counter. Returns 1 if under limit, 0 if at limit.
_LUA_ACQUIRE_CPS = """
local cur = tonumber(redis.call('GET', KEYS[1])) or 0
if cur < tonumber(ARGV[1]) then
    redis.call('INCR', KEYS[1])
    redis.call('EXPIRE', KEYS[1], 1)
    return 1
end
return 0
"""


async def _acquire_cps_slot() -> None:
    """Block until the global CPS limit allows a new call to start (max 1 per second)."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        while True:
            result = await r.eval(_LUA_ACQUIRE_CPS, 1, _CPS_KEY, _CPS_LIMIT)
            if result:
                return
            await asyncio.sleep(0.1)
    except Exception as exc:
        log.error("cps_slot_redis_fail_open", error=str(exc))
        return  # fail open — don't block calls if Redis is down


async def _acquire_lock(campaign_id: str) -> bool:
    """True if we grabbed the lock; False if another worker already holds it."""
    try:
        from app.core.redis import get_redis
        return bool(await (await get_redis()).set(_lock_key(campaign_id), "1", nx=True, ex=_LOCK_TTL))
    except Exception as exc:
        log.error("campaign_lock_redis_fail_open", campaign_id=campaign_id, error=str(exc))
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
    """Return up to `limit` NO_ANSWER or QUEUE_TIMEOUT contacts past their retry delay.

    QUEUE_TIMEOUT contacts (never dialed — org was at its plan's concurrency cap)
    are folded into the same retry pass as NO_ANSWER so a saturated org never
    needs a second dedicated sweep.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=retry_after_minutes)
    result = await session.execute(
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status.in_((ContactStatus.NO_ANSWER, ContactStatus.QUEUE_TIMEOUT)),
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
        # Single source dict, reused for both room metadata and dispatch metadata below --
        # see the dispatch call for why the agent reads it from the dispatch copy, not this one.
        call_meta = {
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
        }
        await lk.room.create_room(
            lk_api.CreateRoomRequest(
                name=room_name,
                # Kept for parity / anyone inspecting the room via the LiveKit dashboard or
                # API -- the agent itself no longer relies on this copy (see dispatch below).
                metadata=json.dumps(call_meta),
            )
        )

        try:
            await asyncio.gather(
                lk.agent_dispatch.create_dispatch(
                    lk_api.CreateAgentDispatchRequest(
                        agent_name=settings.LIVEKIT_AGENT_NAME,
                        room=room_name,
                        # Full metadata (not just agent_template_id) -- this is delivered to
                        # the worker as part of the job assignment itself (JobContext.job.metadata),
                        # available the instant the job starts, with no dependency on room state
                        # sync. Room metadata above races the agent's ctx.connect(): observed in
                        # practice as ctx.room.metadata reading back empty on some jobs even
                        # though create_room() above had already completed, causing the agent to
                        # silently fall back to config.py defaults (wrong call_id, wrong voice).
                        metadata=json.dumps(call_meta),
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
            if sip_code == "429":
                outcome = "congested"
            elif sip_code in _SIP_NO_ANSWER_CODES:
                outcome = "no_answer"
            else:
                outcome = "failed"
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
    answered_at: datetime | None = None,
    duration_cap_seconds: int | None = None,
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

    # duration is measured from when the call was actually answered (SIP call
    # confirmed connected — see wait_until_answered in _place_call), not from
    # Call.started_at. started_at is stamped when the dial attempt's row is
    # created, which can run well before the call connects (DNC checks, trunk/
    # org slot waits, Celery queue backlog) — using it inflates duration by
    # however long that gap was instead of reflecting real call time.
    #
    # Clamped to duration_cap_seconds (the same timeout _wait_for_room_empty
    # enforces before force-closing the room): if the worker process itself
    # stalls or the host sleeps mid-poll, wall-clock now-answered_at can balloon
    # far past any real call length even though the room was already closed.
    duration = None
    if answered_at:
        duration = int((now - answered_at).total_seconds())
        if duration_cap_seconds is not None:
            duration = min(duration, duration_cap_seconds)

    call_values: dict = dict(status=call_status, ended_at=now, duration_seconds=duration)
    if answered_at is not None:
        call_values["answered_at"] = answered_at
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

    # ── Credit billing (1 credit = 1 minute) ───────────────────────────────────
    # Only calls that actually connected consume call-minutes — a no_answer/failed
    # dial attempt's "duration" is just ring/setup time, not billable talk time.
    if place_result == "placed":
        usage = await record_call_credits(session, org_id=campaign.org_id, duration_seconds=duration)
        if usage["overage_minutes"] > 0:
            session.add(CallEvent(
                call_id=call.id,
                event_type="credit_overage_billed",
                payload={
                    "minutes_billed": usage["minutes_billed"],
                    "overage_minutes": usage["overage_minutes"],
                    "overage_cost_cents": usage["overage_cost_cents"],
                    "credits_used_this_period": usage["credits_used_this_period"],
                    "credits_per_month": usage["credits_per_month"],
                },
            ))
            log.info(
                "call_credit_overage_billed",
                call_id=str(call.id),
                org_id=str(campaign.org_id),
                overage_minutes=usage["overage_minutes"],
                overage_cost_cents=usage["overage_cost_cents"],
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
    log.error("recording_fetch_gave_up", call_id=str(call_id), to=to_number)


# ── Per-call coroutine (runs in parallel inside the dispatch loop) ────────────

async def _run_one_call(
    http: aiohttp.ClientSession,
    *,
    owner_user_id: uuid.UUID | None = None,
    **kwargs,
) -> None:
    """Wrapper around _run_one_call_body: gates on the campaign owner's single
    concurrent-call slot (1 call in flight per admin/user, platform-wide,
    shared with test calls) before delegating to the existing org/trunk-level
    flow. Kept as a thin wrapper rather than folded into the body so the
    user-slot release can't be skipped by one of the body's several
    early-return paths.
    """
    contact_id = kwargs["contact_id"]
    contact_phone = kwargs["contact_phone"]

    user_slot_acquired = owner_user_id is None  # no owner to attribute to -- fail open
    if owner_user_id is not None:
        await incr_user_queued(owner_user_id)
        try:
            user_wait_attempts = max(1, settings.CONCURRENCY_MAX_WAIT_SECONDS // _ORG_MAX_WAIT_POLL_INTERVAL)
            for attempt in range(user_wait_attempts):
                if await acquire_user_slot(owner_user_id):
                    user_slot_acquired = True
                    break
                if attempt == 0:
                    log.info("user_at_capacity_queuing", user_id=str(owner_user_id), phone=contact_phone)
                await asyncio.sleep(_ORG_MAX_WAIT_POLL_INTERVAL)
        finally:
            await decr_user_queued(owner_user_id)

    if not user_slot_acquired:
        # This admin/user stayed at their 1-call cap past MAX_WAIT — never dialed.
        log.warning("user_slot_max_wait_exceeded", user_id=str(owner_user_id), phone=contact_phone,
                    max_wait=settings.CONCURRENCY_MAX_WAIT_SECONDS)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(CampaignContact)
                    .where(CampaignContact.id == contact_id)
                    .values(status=ContactStatus.QUEUE_TIMEOUT, last_attempted_at=datetime.now(timezone.utc))
                )
                call_row = await session.get(Call, kwargs["call_id"])
                if call_row:
                    await session.delete(call_row)
        return

    try:
        await _run_one_call_body(http, **kwargs)
    finally:
        if owner_user_id is not None:
            await release_user_slot(owner_user_id)


async def _run_one_call_body(
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
    org_max_concurrent: int,
) -> None:
    """Place one call, wait for it to finish, and finalize — all with its own DB session.

    Acquires BOTH an org-level slot (plan-based cap) and a trunk-level slot
    before dialing; releases both when the call ends, however it ends.
    """

    # ── Org-level concurrency cap (plan-based) — queue-then-reject ────────────
    await incr_queued(org_id)
    org_slot_acquired = False
    try:
        org_wait_attempts = max(1, settings.CONCURRENCY_MAX_WAIT_SECONDS // _ORG_MAX_WAIT_POLL_INTERVAL)
        for attempt in range(org_wait_attempts):
            if await acquire_org_slot(org_id, org_max_concurrent):
                org_slot_acquired = True
                break
            if attempt == 0:
                log.info("org_at_capacity_queuing",
                         org_id=str(org_id), phone=contact_phone, max=org_max_concurrent)
            await asyncio.sleep(_ORG_MAX_WAIT_POLL_INTERVAL)
    finally:
        await decr_queued(org_id)

    if not org_slot_acquired:
        # Org stayed at its plan's concurrency cap past MAX_WAIT — never dialed.
        # QUEUE_TIMEOUT (not PENDING) so it's distinguishable from a fresh contact;
        # _next_retry_batch picks it back up on the normal retry pass.
        log.warning("org_slot_max_wait_exceeded",
                    org_id=str(org_id), phone=contact_phone,
                    max_wait=settings.CONCURRENCY_MAX_WAIT_SECONDS)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(CampaignContact)
                    .where(CampaignContact.id == contact_id)
                    .values(status=ContactStatus.QUEUE_TIMEOUT, last_attempted_at=datetime.now(timezone.utc))
                )
                # Remove the pre-created Call record — the call was never actually placed.
                call_row = await session.get(Call, call_id)
                if call_row:
                    await session.delete(call_row)
        return

    try:
        # ── Per-trunk concurrency cap (unchanged) ──────────────────────────────
        # Wait up to 5 minutes for a slot on this trunk (max 5 concurrent calls per phone number)
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
            # Respect global CPS limit — at most 1 new call per second across all campaigns
            await _acquire_cps_slot()

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

            if place_result == "congested":
                # Vobiz still rejected with 429 despite CPS limiting — reset to PENDING for retry
                log.warning("cps_congested_resetting_contact",
                            trunk=livekit_trunk_id, phone=contact_phone)
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await session.execute(
                            update(CampaignContact)
                            .where(CampaignContact.id == contact_id)
                            .values(status=ContactStatus.PENDING)
                        )
                        call_row = await session.get(Call, call_id)
                        if call_row:
                            await session.delete(call_row)
                return

            answered_at: datetime | None = None
            if place_result == "placed":
                # _place_call uses wait_until_answered=True, so reaching here
                # means the call was just confirmed answered — this is the
                # correct anchor for duration, not the row's started_at.
                answered_at = datetime.now(timezone.utc)
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
            try:
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
                            answered_at=answered_at,
                            duration_cap_seconds=max_duration + 60,
                        )
            except Exception:
                log.exception("finalize_error", call_id=str(call_id), contact_id=str(contact_id))
                # Ensure contact is never stuck in DIALING after a finalization crash
                try:
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            await session.execute(
                                update(CampaignContact)
                                .where(CampaignContact.id == contact_id)
                                .values(status=ContactStatus.FAILED)
                            )
                            await session.execute(
                                update(Campaign)
                                .where(Campaign.id == uuid.UUID(campaign_id))
                                .values(failed_count=Campaign.failed_count + 1)
                            )
                except Exception:
                    log.exception("finalize_recovery_error", contact_id=str(contact_id))

            if place_result == "placed":
                async with AsyncSessionLocal() as session:
                    vobiz_creds = await resolve_vobiz_credentials(
                        session, org_id=org_id, livekit_trunk_id=livekit_trunk_id, campaign_id=uuid.UUID(campaign_id),
                    )
                if vobiz_creds:
                    vobiz_auth_id, vobiz_auth_token = vobiz_creds
                    asyncio.create_task(_save_recording_async(
                        call_id=call_id,
                        to_number=contact_phone,
                        called_after=call_started_at_utc or datetime.now(timezone.utc) - timedelta(minutes=30),
                        auth_id=vobiz_auth_id,
                        auth_token=vobiz_auth_token,
                    ))
        finally:
            await _release_trunk_slot(livekit_trunk_id)
    finally:
        await release_org_slot(org_id)


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

        # Defensive re-check: the launch endpoint already blocks starting a
        # campaign for a suspended org, but a subscription can lapse mid-run
        # (Razorpay webhook: subscription.halted/cancelled). Pause rather than
        # silently stop so it resumes on its own once the org reactivates.
        async with AsyncSessionLocal() as session:
            org = await session.get(Organization, campaign.org_id)
            if org and not org.is_active:
                async with session.begin():
                    await session.execute(
                        update(Campaign).where(Campaign.id == campaign.id).values(status=CampaignStatus.PAUSED)
                    )
                log.warning("campaign_paused_org_inactive", campaign_id=campaign_id, org_id=str(campaign.org_id))
                return

            # Same idea, but for credits running out mid-run instead of the org
            # going inactive — stop dialing before more overage accumulates.
            if not await has_credits_remaining(session, campaign.org_id):
                async with session.begin():
                    await session.execute(
                        update(Campaign).where(Campaign.id == campaign.id).values(status=CampaignStatus.PAUSED)
                    )
                log.warning("campaign_paused_credits_exhausted", campaign_id=campaign_id, org_id=str(campaign.org_id))
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
                            CampaignContact.status.in_((ContactStatus.NO_ANSWER, ContactStatus.QUEUE_TIMEOUT)),
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
                    org_max_concurrent = await resolve_org_max_concurrent(session, campaign.org_id)
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

        # ── Run batch concurrently — all contacts in this batch call in parallel ──
        # return_exceptions=True ensures one failed call never aborts the rest.
        results = await asyncio.gather(*[
            _run_one_call(
                http,
                campaign_id=campaign_id,
                org_id=campaign.org_id,
                livekit_trunk_id=livekit_trunk_id,
                sip_caller_id=sip_caller_id,
                org_max_concurrent=org_max_concurrent,
                owner_user_id=campaign.created_by_id,
                **tmpl_kwargs,
                **d,
            )
            for d in batch
        ], return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                log.error("batch_call_unhandled_error",
                          phone=batch[i]["contact_phone"],
                          error=str(r))

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

    # Stagger DB startup — prevents connection spike when many campaigns launch simultaneously
    await asyncio.sleep(random.uniform(0, 3))

    # Reset any contacts stuck in DIALING from a previous crashed run
    await _reset_stale_dialing(campaign_id)

    log.info("campaign_dispatcher_start", campaign_id=campaign_id)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
            await _dispatch_loop(http, campaign_id)
    except Exception:
        log.exception("campaign_dispatcher_error", campaign_id=campaign_id)
        # Mark campaign FAILED so the UI reflects the crash (not stuck in RUNNING)
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await session.execute(
                        update(Campaign)
                        .where(Campaign.id == uuid.UUID(campaign_id))
                        .values(status=CampaignStatus.FAILED)
                    )
        except Exception:
            log.exception("campaign_mark_failed_error", campaign_id=campaign_id)
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
    trunk_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Place a single test call for an agent template (no campaign).

    The caller (app/api/agents.py) already acquired this user's 1-call slot
    before dispatching this task -- released here once the call is fully
    done, however it ends (answered+finished, no_answer, failed, or an
    unhandled exception), so the admin is never left locked out by a slot
    that never gets freed. Thin wrapper so the release logic can't be
    accidentally skipped by one of the several early-return paths below.
    """
    from uuid import UUID as _UUID

    try:
        await _run_test_call_body(agent_id, phone_number, call_id, org_id, trunk_id)
    finally:
        if user_id:
            await release_user_slot(_UUID(user_id))


async def _run_test_call_body(
    agent_id: str,
    phone_number: str,
    call_id: str,
    org_id: str,
    trunk_id: str | None = None,
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

        # Caller explicitly picked a "From" number in the test-call dialog —
        # use that exact trunk rather than guessing via is_default, which can
        # silently point at a stale/misconfigured trunk (see: trunk with no
        # Vobiz credentials left marked is_default after a later reconnect).
        chosen_trunk = None
        if trunk_id:
            chosen_trunk = await session.scalar(
                select(SipTrunk).where(
                    SipTrunk.id == _UUID(trunk_id),
                    SipTrunk.org_id == _UUID(org_id),
                    SipTrunk.is_active.is_(True),
                    SipTrunk.deleted_at.is_(None),
                )
            )
        if chosen_trunk is None:
            chosen_trunk = await session.scalar(
                select(SipTrunk).where(
                    SipTrunk.org_id == _UUID(org_id),
                    SipTrunk.is_default.is_(True),
                    SipTrunk.is_active.is_(True),
                    SipTrunk.deleted_at.is_(None),
                )
            )
        resolved_trunk_id = chosen_trunk.id if chosen_trunk else None
        livekit_trunk_id = (chosen_trunk.livekit_trunk_id if chosen_trunk else None) or settings.DEFAULT_SIP_TRUNK_ID
        sip_caller_id    = (chosen_trunk.caller_id        if chosen_trunk else None) or settings.DEFAULT_SIP_CALLER_ID

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

        answered_at: datetime | None = None
        if place_result == "placed":
            # _place_call uses wait_until_answered=True, so reaching here means
            # the call was just confirmed answered — the correct anchor for
            # duration. Call.started_at is stamped when the row is created
            # (API request time, before this task is even picked up off the
            # Celery queue), so it can be far earlier than the actual dial and
            # would otherwise inflate duration by however long the task sat queued.
            answered_at = datetime.now(timezone.utc)
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
            duration = None
            if answered_at:
                call_row.answered_at = answered_at
                duration = min(int((now - answered_at).total_seconds()), 660)
                call_row.duration_seconds = duration

            # Same billing rule as campaign calls (see _finalize_call above):
            # a test call that actually connected consumes call-minutes too —
            # it's a real call on real infrastructure, not a free simulation.
            if place_result == "placed":
                usage = await record_call_credits(session, org_id=_UUID(org_id), duration_seconds=duration)
                if usage["overage_minutes"] > 0:
                    session.add(CallEvent(
                        call_id=call_row.id,
                        event_type="credit_overage_billed",
                        payload={
                            "minutes_billed": usage["minutes_billed"],
                            "overage_minutes": usage["overage_minutes"],
                            "overage_cost_cents": usage["overage_cost_cents"],
                            "credits_used_this_period": usage["credits_used_this_period"],
                            "credits_per_month": usage["credits_per_month"],
                        },
                    ))

            await session.commit()

    log.info("test_call_done", call_id=call_id, result=place_result)

    if place_result == "placed":
        # Awaited directly (not fire-and-forget like _run_one_call) — a test call
        # is a single one-off task with nothing else keeping its asyncio.run()
        # loop alive, so a asyncio.create_task() here would be silently killed
        # when this function returns and the loop closes before the task runs.
        async with AsyncSessionLocal() as session:
            vobiz_creds = await resolve_vobiz_credentials(
                session, org_id=_UUID(org_id), trunk_id=resolved_trunk_id, livekit_trunk_id=livekit_trunk_id,
            )
        if vobiz_creds:
            vobiz_auth_id, vobiz_auth_token = vobiz_creds
            await _save_recording_async(
                call_id=_UUID(call_id),
                to_number=phone_number,
                called_after=answered_at or datetime.now(timezone.utc) - timedelta(minutes=30),
                auth_id=vobiz_auth_id,
                auth_token=vobiz_auth_token,
            )


@celery_app.task(
    name="app.workers.tasks.campaign.place_test_call",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def place_test_call(
    self, agent_id: str, phone_number: str, call_id: str, org_id: str,
    trunk_id: str | None = None, user_id: str | None = None,
) -> None:
    """Place a single test call for an agent template (no campaign)."""
    asyncio.run(_run_test_call_async(agent_id, phone_number, call_id, org_id, trunk_id, user_id))


@celery_app.task(
    name="app.workers.tasks.campaign.fetch_recording_for_inbound_call",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def fetch_recording_for_inbound_call(self, call_id: str, trunk_id: str) -> None:
    """
    Inbound calls have no wrapping campaign/test-call task the way outbound
    ones do (the whole call is handled standalone by the agent process), so
    /agent-report (app/api/calls.py) enqueues this directly once an inbound
    call ends, reusing the same _save_recording_async()/resolve_vobiz_credentials()
    helpers outbound already uses.
    """
    asyncio.run(_fetch_recording_for_inbound_call_async(call_id, trunk_id))


async def _fetch_recording_for_inbound_call_async(call_id: str, trunk_id: str) -> None:
    from uuid import UUID as _UUID

    async with AsyncSessionLocal() as session:
        trunk = await session.get(SipTrunk, _UUID(trunk_id))
        if not trunk:
            log.error("inbound_recording_fetch_missing_trunk", call_id=call_id, trunk_id=trunk_id)
            return
        org_id = trunk.org_id
        to_number = trunk.caller_id
        vobiz_creds = await resolve_vobiz_credentials(session, org_id=org_id, trunk_id=trunk.id)

    if not vobiz_creds:
        log.warning("inbound_recording_fetch_no_creds", call_id=call_id, trunk_id=trunk_id)
        return
    vobiz_auth_id, vobiz_auth_token = vobiz_creds

    await _save_recording_async(
        call_id=_UUID(call_id),
        # Vobiz's Recording API labels the DID that was DIALED as "to_number" --
        # for an inbound call that's the org's own number, not the caller's.
        to_number=to_number,
        called_after=datetime.now(timezone.utc) - timedelta(minutes=30),
        auth_id=vobiz_auth_id,
        auth_token=vobiz_auth_token,
    )


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


# ── Stale-pending-call detector ─────────────────────────────────────────────
# The agent POSTs the real outcome/summary/transcript to /api/calls/{id}/agent-report
# right after each call ends. If that POST never arrives (agent crash, network
# blip, backend misconfiguration), the Call row is silently left at its DB
# default (outcome=PENDING) forever — the transcript/summary data itself only
# ever existed in the agent process's memory and can't be recovered after the
# fact. This task can't get that data back; it exists purely so a stuck call
# shows up in logs instead of going unnoticed indefinitely.
_STALE_PENDING_AGE = timedelta(minutes=10)


@celery_app.task(name="app.workers.tasks.campaign.flag_stale_pending_calls", bind=True)
def flag_stale_pending_calls(self) -> None:
    """Beat task (every 60 s): log any COMPLETED call still stuck at outcome=PENDING."""
    asyncio.run(_flag_stale_pending_async())


async def _flag_stale_pending_async() -> None:
    cutoff = datetime.now(timezone.utc) - _STALE_PENDING_AGE
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Call.id, Call.phone_number, Call.campaign_id, Call.ended_at).where(
                Call.status == CallStatus.COMPLETED,
                Call.outcome == CallOutcome.PENDING,
                Call.ended_at.is_not(None),
                Call.ended_at <= cutoff,
            )
        )
        stale = rows.all()

    for call_id, phone_number, campaign_id, ended_at in stale:
        log.warning(
            "stale_pending_call",
            call_id=str(call_id),
            phone_number=phone_number,
            campaign_id=str(campaign_id) if campaign_id else None,
            ended_at=ended_at.isoformat() if ended_at else None,
            note="agent-report likely never arrived — check agent logs for this call_id",
        )
