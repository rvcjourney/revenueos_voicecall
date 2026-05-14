"""
app/core/redis.py — Shared async Redis connection pool.
One pool per process; get_redis() is safe to call repeatedly.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, creating the pool on first call."""
    global _pool, _client
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    if _client is None:
        _client = aioredis.Redis(connection_pool=_pool)
    return _client


async def close_redis() -> None:
    """Close all connections. Called on application shutdown."""
    global _pool, _client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def redis_key(*parts: str) -> str:
    """Build a namespaced key: motm:{part1}:{part2}:..."""
    return f"{settings.REDIS_PREFIX}:{':'.join(parts)}"
