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

import math

import structlog

from app.core.exceptions import RateLimitedError
from app.core.redis import redis_key

log = structlog.get_logger(__name__)


async def enforce_rate_limit(
    bucket: str,
    identifier: str,
    *,
    limit: int,
    window_seconds: int,
    message_template: str | None = None,
) -> None:
    """Raises RateLimitedError once `identifier` has made more than `limit`
    calls to `bucket` within the trailing `window_seconds`-second window.

    `message_template` (optional) may contain a `{minutes}` placeholder,
    filled in with how long until the window resets (rounded up, minimum 1)
    once the limit is actually hit -- lets a caller give a specific message
    ("Test call limit reached: 3 per hour. Try again in 42 minute(s).")
    instead of the generic default. Every caller also gets the same
    information back machine-readably via RateLimitedError.retry_after_seconds
    regardless of whether message_template is given.
    """
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
        ttl = await r.ttl(key)
        retry_after = ttl if ttl and ttl > 0 else window_seconds
        message = (
            message_template.format(minutes=max(1, math.ceil(retry_after / 60)))
            if message_template
            else None
        )
        raise RateLimitedError(message=message, retry_after_seconds=retry_after)


def client_ip(request) -> str:
    """Best-effort caller IP. Trusts X-Forwarded-For's first hop since this
    always sits behind the VPS's own reverse proxy in production -- not
    meant to be spoof-proof, just enough to bucket distinct callers for
    rate-limiting purposes."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
