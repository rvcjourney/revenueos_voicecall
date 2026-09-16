"""
app/database.py — SQLAlchemy 2.0 async engine, session factory, and base model.
"""
from __future__ import annotations

import asyncio
import contextlib
import ssl
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# The API engine below pools connections (AsyncAdaptedQueuePool, SQLAlchemy's
# async default) -- DATABASE_URL points at Supabase's SESSION-mode pooler
# (aws-*.pooler.supabase.com:5432), which dedicates one Postgres backend to
# a connection for its whole lifetime, unlike transaction-mode (port 6543)
# which can reassign backends mid-connection and previously broke pooling
# here with live "prepared statement ... does not exist" errors. Confirmed
# safe against the current URL with a 60-query concurrent pooled-connection
# stress test (default asyncpg prepared-statement caching, no errors) before
# switching this from NullPool. If DATABASE_URL ever moves back to the
# transaction-mode pooler (port 6543), this must revert to NullPool.
#
# Without pooling, every single request paid a fresh TCP+TLS+auth handshake
# to Supabase before its first query could even run -- measured at ~2s per
# connection vs ~0.3-0.5s reusing one, i.e. the dominant cause of "everything
# feels slow to load" across the app.
#
# Deliberately NOT using pool_pre_ping: measured it adding a full extra
# round-trip to every single checkout, ~3x'ing steady-state per-query time
# here (the ping itself, before the real query even runs) -- a bad trade
# given the whole point of this pool is speed. pool_recycle below already
# proactively retires connections well before they'd realistically go stale
# server-side; the rare case where one still dies while pooled just fails
# that one request (SQLAlchemy discards a connection that errors), and the
# next request gets a fresh one -- self-healing, not a cascading outage.
#
# Sized down from 5/5 after a live outage on 2026-09-15: Supabase's
# session-mode pooler hard-caps the WHOLE platform (api + worker + agent +
# any manual script) at 15 concurrent connections. At 5/5, this engine's own
# steady-state floor alone was 4 gunicorn workers * pool_size(5) = 20 --
# already over the cap with celery and everything else not even counted.
# 2/1 keeps the steady floor at 4*2=8 and the burst ceiling at 4*3=12,
# leaving headroom for the worker (see docker-compose.yml's worker
# --concurrency comment) and ad-hoc scripts. If gunicorn's worker count
# (backend/Dockerfile) or DATABASE_URL's Supabase compute tier ever change,
# re-derive these against the new connection cap rather than raising them
# back to old values.
_API_POOL_SIZE = 2
_API_POOL_MAX_OVERFLOW = 1
_API_POOL_RECYCLE_SECONDS = 300

# Each request opens a brand-new asyncpg connection, which means a single
# transient DNS/network hiccup (e.g. Windows getaddrinfo error 11001)
# surfaces as a hard failure on whatever request hit it. Retry the raw
# connect a few times with a short backoff before giving up — real auth/config
# errors (bad password, unknown database) aren't OSErrors and still fail immediately.
_CONNECT_RETRIES = 3
_CONNECT_RETRY_DELAY = 0.5


async def _connect_with_retry(*args: Any, **kwargs: Any) -> asyncpg.Connection:
    last_exc: OSError | None = None
    for attempt in range(_CONNECT_RETRIES):
        try:
            return await asyncpg.connect(*args, **kwargs)
        except OSError as exc:
            last_exc = exc
            if attempt < _CONNECT_RETRIES - 1:
                await asyncio.sleep(_CONNECT_RETRY_DELAY * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver."""
    for sync_prefix in ("postgresql://", "postgres://"):
        if url.startswith(sync_prefix):
            return url.replace(sync_prefix, "postgresql+asyncpg://", 1)
    return url  # already has asyncpg or another async driver


def _connect_args() -> dict[str, Any]:
    args: dict[str, Any] = {
        # Supabase transaction-mode pooler multiplexes connections across
        # backends. asyncpg uses sequential names (__asyncpg_stmt_N__) that
        # collide when two pooled connections hit the same backend.
        # statement_cache_size=0 disables caching; prepared_statement_name_func
        # generates a UUID per statement so names never collide.
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__",
        "async_creator_fn": _connect_with_retry,
    }
    if settings.DB_SSL_REQUIRED:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        args["ssl"] = ctx
    return args


def _make_engine(url: str):
    # Pooled (see module docstring above for why this is safe against the
    # currently-configured session-mode pooler URL). Each of gunicorn's 4
    # worker processes gets its own engine/pool, so peak connections from
    # the API alone is bounded at 4 * (pool_size + max_overflow) = 12 --
    # see _API_POOL_SIZE's comment for why this must stay well under
    # Supabase's platform-wide 15-connection cap.
    return create_async_engine(
        _async_url(url),
        echo=settings.DB_ECHO,
        future=True,
        connect_args=_connect_args(),
        pool_size=_API_POOL_SIZE,
        max_overflow=_API_POOL_MAX_OVERFLOW,
        pool_recycle=_API_POOL_RECYCLE_SECONDS,
    )


engine = _make_engine(settings.DATABASE_URL)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields a session, commits on success, rolls back on exception.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextlib.asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for use outside FastAPI (Celery tasks, scripts).
    Identical commit/rollback semantics to get_db().
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    """Return True if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Close all pooled connections. Called on application shutdown."""
    await engine.dispose()


def make_worker_session_factory():
    """
    NullPool session factory for Celery workers.

    Celery prefork workers call asyncio.run() for every task, creating a new
    event loop each time. A pooled engine reuses asyncpg connections tied to
    the PREVIOUS event loop → 'Future attached to a different loop' crash.

    NullPool creates a brand-new DB connection for every session and closes it
    when the session ends — nothing is ever reused across event loops.
    """
    from sqlalchemy.pool import NullPool
    worker_engine = create_async_engine(
        _async_url(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args=_connect_args(),
        echo=settings.DB_ECHO,
        future=True,
    )
    return async_sessionmaker(
        bind=worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
