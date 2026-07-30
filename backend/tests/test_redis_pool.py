"""
tests/test_redis_pool.py — app/core/redis.py cross-event-loop safety.

Regression test for a production bug: Celery worker tasks each run inside
their own asyncio.run() (app/workers/tasks/campaign.py), a fresh event loop
every time. A module-level cached Redis pool/client created under one task's
loop raised "RuntimeError: Event loop is closed" the next time a different
task tried to reuse it. get_redis() must detect the stale pool and recreate
it instead of reusing it, while still reusing the client within the SAME loop.

Does not require a real Redis server: ConnectionPool.from_url()/Redis() are
lazy -- no network I/O happens until a command is actually sent, and this
test only inspects object identity, never issues a real command.
"""
from __future__ import annotations

import asyncio

import app.core.redis as redis_module


def _reset_module_state():
    redis_module._pool = None
    redis_module._client = None
    redis_module._pool_loop = None


def test_get_redis_reuses_client_within_the_same_event_loop():
    _reset_module_state()

    async def _run():
        c1 = await redis_module.get_redis()
        c2 = await redis_module.get_redis()
        return c1, c2

    c1, c2 = asyncio.run(_run())
    assert c1 is c2


def test_get_redis_recreates_pool_across_separate_asyncio_run_calls():
    """Simulates two separate Celery task invocations, each its own asyncio.run()."""
    _reset_module_state()

    async def _task():
        await redis_module.get_redis()
        return id(redis_module._pool)

    pool_id_1 = asyncio.run(_task())
    # The first task's event loop is now closed. A naive cached pool would be
    # unusable here -- this must NOT raise "Event loop is closed".
    pool_id_2 = asyncio.run(_task())
    pool_id_3 = asyncio.run(_task())

    assert pool_id_1 != pool_id_2
    assert pool_id_2 != pool_id_3


async def test_close_redis_clears_all_cached_state():
    _reset_module_state()
    await redis_module.get_redis()
    assert redis_module._pool is not None

    await redis_module.close_redis()

    assert redis_module._pool is None
    assert redis_module._client is None
    assert redis_module._pool_loop is None
