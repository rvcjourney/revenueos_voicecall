"""
app/core/redis.py — Shared async Redis connection pool.
One pool per process; get_redis() is safe to call repeatedly.

The FastAPI app runs one long-lived event loop for its whole life, so caching
the pool/client at module level is safe there. The Celery worker is
different: each task runs its own asyncio.run(...) (app/workers/tasks/campaign.py),
which is a brand-new event loop every time. A pool/client created under one
task's loop is unusable once that loop closes (raises "RuntimeError: Event
loop is closed" on the next use) — so get_redis() detects a stale pool (bound
to a loop that is no longer the current one, or that has since closed) and
transparently recreates it under the current loop instead of reusing it.
"""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from app.config import settings

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, (re)creating the pool as needed."""
    global _pool, _client, _pool_loop

    current_loop = asyncio.get_running_loop()
    if _pool is not None and (_pool_loop is not current_loop or _pool_loop.is_closed()):
        # Stale pool from a previous, now-closed event loop (e.g. a prior
        # Celery task's asyncio.run()). Can't await cleanup on a dead loop —
        # just drop the references and let them be garbage collected.
        _pool = None
        _client = None

    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        _pool_loop = current_loop
    if _client is None:
        _client = aioredis.Redis(connection_pool=_pool)
    return _client


async def close_redis() -> None:
    """Close all connections. Called on application shutdown."""
    global _pool, _client, _pool_loop
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
    _pool_loop = None


def redis_key(*parts: str) -> str:
    """Build a namespaced key: motm:{part1}:{part2}:..."""
    return f"{settings.REDIS_PREFIX}:{':'.join(parts)}"
