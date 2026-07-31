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
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool is required for PgBouncer transaction mode (port 6543): each
# session opens a fresh physical connection and closes it when done, so no
# pooled connection can straddle a PgBouncer backend swap mid-use. A prior
# attempt to reuse pooled connections here (relying on statement_cache_size=0
# + UUID-named prepared statements alone) still produced live
# "prepared statement ... does not exist" errors under real traffic — that
# protects against *client-side* statement-cache reuse, not against PgBouncer
# reassigning the backend between two uses of the same pooled connection.
# Do not reintroduce SQLAlchemy-level pooling here without first moving off
# PgBouncer transaction-mode pooling (e.g. a direct Postgres connection or
# asyncpg's own pool instead).

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
    # NullPool: required for PgBouncer transaction mode (port 6543).
    # Each session opens a fresh connection and closes it when done — no
    # pooled state leaks across requests, so prepared statements are always
    # on the same backend that created them.
    return create_async_engine(
        _async_url(url),
        echo=settings.DB_ECHO,
        future=True,
        connect_args=_connect_args(),
        poolclass=NullPool,
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
