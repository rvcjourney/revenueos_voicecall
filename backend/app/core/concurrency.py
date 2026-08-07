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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.subscription import Subscription

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
_MAX_CONCURRENT_CACHE_TTL = 60   # seconds a resolved plan limit is cached
DEFAULT_MAX_CONCURRENT_PER_ORG = 10  # fallback when an org has no active subscription/plan

# Hard cap, not plan-based: whoever launched a campaign (or placed a test call)
# can only ever have ONE of their own calls in flight at a time, platform-wide
# across every campaign and test call they own. Independent of the org-level
# and per-trunk caps above — a call must clear all three.
DEFAULT_MAX_CONCURRENT_PER_USER = 1


def org_slot_key(org_id: UUID) -> str:
    return f"motm:concurrency:{org_id}"


def org_queued_key(org_id: UUID) -> str:
    return f"motm:concurrency:queued:{org_id}"


def _org_max_cache_key(org_id: UUID) -> str:
    return f"motm:concurrency:max:{org_id}"


async def resolve_org_max_concurrent(session: AsyncSession, org_id: UUID) -> int:
    """
    The org's max_concurrent_calls, from its active subscription's plan.
    Falls back to DEFAULT_MAX_CONCURRENT_PER_ORG if there's no active sub/plan.

    Cached in Redis for _MAX_CONCURRENT_CACHE_TTL seconds since this is looked
    up on every dial attempt and the plan rarely changes.
    """
    cache_key = _org_max_cache_key(org_id)
    redis = None
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached is not None:
            return int(cached)
    except Exception:
        redis = None

    max_concurrent = DEFAULT_MAX_CONCURRENT_PER_ORG
    sub = await session.scalar(
        select(Subscription).where(
            Subscription.org_id == org_id,
            Subscription.deleted_at.is_(None),
            Subscription.status.in_(("trialing", "active")),
        )
    )
    if sub:
        plan = await session.get(Plan, sub.plan_id)
        if plan and plan.max_concurrent_calls:
            max_concurrent = plan.max_concurrent_calls

    if redis is not None:
        try:
            await redis.set(cache_key, max_concurrent, ex=_MAX_CONCURRENT_CACHE_TTL)
        except Exception:
            pass

    return max_concurrent


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


async def get_current_usage(session: AsyncSession, org_id: UUID) -> dict:
    """Read-only snapshot for GET /api/usage/concurrency: {in_use, max, queued}."""
    max_concurrent = await resolve_org_max_concurrent(session, org_id)
    in_use = 0
    queued = 0
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        in_use = int(await r.get(org_slot_key(org_id)) or 0)
        queued = int(await r.get(org_queued_key(org_id)) or 0)
    except Exception:
        pass
    return {"in_use": in_use, "max": max_concurrent, "queued": queued}
