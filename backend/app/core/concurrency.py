"""
app/core/concurrency.py — Shared per-org concurrency primitives.

Used by both the campaign dispatcher (app/workers/tasks/campaign.py) and the
usage read API (app/api/usage.py) so the Redis key names and the org-plan
resolution logic can never drift between the two.

Per-trunk concurrency is a separate, lower-level limit that stays in
app/workers/tasks/campaign.py — it's a worker-only concern with no read API.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sip import SipTrunk

# Same atomic incr-if-under-max pattern used for per-trunk slots
# (app/workers/tasks/campaign.py's _LUA_ACQUIRE_SLOT).
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

_SLOT_KEY_TTL = 3600            # 1-hour safety TTL — prevents a stuck counter after a crash

# Per-number allowance, not a flat per-org cap — a deliberate business
# decision, not a per-plan entitlement. Plan.max_concurrent_calls is
# intentionally no longer consulted here (it still exists as an
# admin-editable field, but has no effect on enforcement). An org with one
# connected number gets exactly this many concurrent calls, same as always;
# an org with N active numbers gets N times this, since each additional
# number is a genuinely separate Vobiz account/line with its own capacity
# (see resolve_org_max_concurrent below) — not raising what a single-number
# org could already safely do, only unlocking real capacity an org has
# actually paid for by connecting more numbers.
DEFAULT_MAX_CONCURRENT_PER_ORG = 3

# Hard cap, not plan-based: whoever launched a campaign (or placed a test call)
# can only ever have ONE of their own calls in flight at a time, platform-wide
# across every campaign and test call they own. Independent of the org-level
# and per-trunk caps above — a call must clear all three.
DEFAULT_MAX_CONCURRENT_PER_USER = 1


def org_slot_key(org_id: UUID) -> str:
    return f"motm:concurrency:{org_id}"


def org_queued_key(org_id: UUID) -> str:
    return f"motm:concurrency:queued:{org_id}"


async def resolve_org_max_concurrent(session: AsyncSession, org_id: UUID) -> int:
    """
    Concurrent-call cap for the org, scaled by how many phone numbers it has
    actually connected and verified (SipTrunk.is_active) — an org with 2+
    numbers can run that many more calls (and campaigns) at once instead of
    sharing the same flat pool as an org with a single number, since each
    additional number is its own independent Vobiz account/line. A
    single-number org's cap is unchanged from before this scaled (still
    exactly DEFAULT_MAX_CONCURRENT_PER_ORG) — this only unlocks capacity for
    orgs that connected more numbers, it never raises anyone's existing cap.
    The real ceiling on what any one number can push through stays
    independently enforced by the per-trunk slot cap and per-trunk CPS
    limiter in app/workers/tasks/campaign.py, so this can't overcommit a
    single number beyond what it already safely handles on its own.
    """
    active_trunks = await session.scalar(
        select(func.count()).where(
            SipTrunk.org_id == org_id,
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
    )
    return DEFAULT_MAX_CONCURRENT_PER_ORG * max(1, active_trunks or 0)


async def acquire_org_slot(org_id: UUID, max_concurrent: int) -> bool:
    """
    Atomically grab one of the org's plan-based concurrent-call slots.
    Returns True if acquired, False if the org is at capacity.
    Falls back to True (allow) if Redis is unavailable.
    """
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        result = await r.eval(_LUA_ACQUIRE_SLOT, 1, org_slot_key(org_id), max_concurrent, _SLOT_KEY_TTL)
        return bool(result)
    except Exception:
        return True  # fail open — don't block calls if Redis is down


async def release_org_slot(org_id: UUID) -> None:
    """Decrement the org's active-call counter. Floors at 0 to guard against bugs."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        count = await r.decr(org_slot_key(org_id))
        if count < 0:
            await r.set(org_slot_key(org_id), 0)
    except Exception:
        pass  # best-effort


async def incr_queued(org_id: UUID) -> None:
    """Mark one contact as currently waiting for an org slot (visible via the usage API)."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.incr(org_queued_key(org_id))
        await r.expire(org_queued_key(org_id), _SLOT_KEY_TTL)
    except Exception:
        pass


async def decr_queued(org_id: UUID) -> None:
    """Counterpart to incr_queued — always call in a finally so it can't leak."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        count = await r.decr(org_queued_key(org_id))
        if count < 0:
            await r.set(org_queued_key(org_id), 0)
    except Exception:
        pass


def user_slot_key(user_id: UUID) -> str:
    return f"motm:concurrency:user:{user_id}"


def user_queued_key(user_id: UUID) -> str:
    return f"motm:concurrency:queued:user:{user_id}"


async def incr_user_queued(user_id: UUID) -> None:
    """Mark one contact as currently waiting on this user's single call slot."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.incr(user_queued_key(user_id))
        await r.expire(user_queued_key(user_id), _SLOT_KEY_TTL)
    except Exception:
        pass


async def decr_user_queued(user_id: UUID) -> None:
    """Counterpart to incr_user_queued — always call in a finally so it can't leak."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        count = await r.decr(user_queued_key(user_id))
        if count < 0:
            await r.set(user_queued_key(user_id), 0)
    except Exception:
        pass


async def get_user_queued(user_id: UUID) -> int:
    """Read-only snapshot of how many of this user's contacts are waiting on their 1-call slot."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        return int(await r.get(user_queued_key(user_id)) or 0)
    except Exception:
        return 0


async def acquire_user_slot(user_id: UUID, max_concurrent: int = DEFAULT_MAX_CONCURRENT_PER_USER) -> bool:
    """
    Atomically grab the user's single concurrent-call slot. Returns True if
    acquired, False if that user already has a call in flight.
    Falls back to True (allow) if Redis is unavailable.
    """
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        result = await r.eval(_LUA_ACQUIRE_SLOT, 1, user_slot_key(user_id), max_concurrent, _SLOT_KEY_TTL)
        return bool(result)
    except Exception:
        return True  # fail open — don't block calls if Redis is down


async def release_user_slot(user_id: UUID) -> None:
    """Decrement the user's active-call counter. Floors at 0 to guard against bugs."""
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        count = await r.decr(user_slot_key(user_id))
        if count < 0:
            await r.set(user_slot_key(user_id), 0)
    except Exception:
        pass  # best-effort


async def get_current_usage(session: AsyncSession, org_id: UUID, user_id: UUID | None = None) -> dict:
    """
    Read-only snapshot for GET /api/usage/concurrency: {in_use, max, queued, my_queued}.

    `my_queued` (only populated when user_id is given) is the caller's own
    count of contacts waiting on their personal 1-call slot — distinct from
    `queued`, which is the org-wide count waiting on the plan's shared cap.
    A user can see a nonzero my_queued (their second campaign queuing behind
    their first) while the org-wide queued is 0 (plenty of org capacity free).
    """
    max_concurrent = await resolve_org_max_concurrent(session, org_id)
    in_use = 0
    queued = 0
    my_queued = 0
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        in_use = int(await r.get(org_slot_key(org_id)) or 0)
        queued = int(await r.get(org_queued_key(org_id)) or 0)
        if user_id is not None:
            my_queued = await get_user_queued(user_id)
    except Exception:
        pass
    return {"in_use": in_use, "max": max_concurrent, "queued": queued, "my_queued": my_queued}
