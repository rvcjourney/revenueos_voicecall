"""
app/core/rate_limit.py — Redis-backed fixed-window rate limiting.

Same INCR-then-EXPIRE-once pattern as the OTP resend cooldown
(app/api/auth.py:resend_otp), just generalized to N-per-window instead of a
single cooldown flag. A small race on the very first request in a window
(two concurrent requests both seeing count==1 and both calling EXPIRE) is
harmless -- both calls set the same TTL.

Fails open on Redis errors: a rate limiter that itself takes the API down
when Redis hiccups is worse than temporarily unlimited auth attempts.
"""
from __future__ import annotations

import structlog

from app.core.exceptions import RateLimitedError
from app.core.redis import redis_key

log = structlog.get_logger(__name__)


async def enforce_rate_limit(bucket: str, identifier: str, *, limit: int, window_seconds: int) -> None:
    """Raises RateLimitedError once `identifier` has made more than `limit`
    calls to `bucket` within the trailing `window_seconds`-second window."""
    try:
        # Imported here, not at module load -- tests patch app.core.redis.get_redis
        # per-call (conftest.py's fake_redis fixture); a module-level import would
        # bind the pre-patch function object and never see the fake.
        from app.core.redis import get_redis
        r = await get_redis()
        key = redis_key("ratelimit", bucket, identifier)
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window_seconds)
    except Exception as exc:
        log.warning("rate_limit_check_failed", bucket=bucket, error=str(exc))
        return

    if current > limit:
        raise RateLimitedError()


def client_ip(request) -> str:
    """Best-effort caller IP. Trusts X-Forwarded-For's first hop since this
    always sits behind the VPS's own reverse proxy in production -- not
    meant to be spoof-proof, just enough to bucket distinct callers for
    rate-limiting purposes."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
