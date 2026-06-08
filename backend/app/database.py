"""
app/database.py — SQLAlchemy 2.0 async engine, session factory, and base model.
"""
from __future__ import annotations

import contextlib
import ssl
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


def _async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver."""
    for sync_prefix in ("postgresql://", "postgres://"):
        if url.startswith(sync_prefix):
            return url.replace(sync_prefix, "postgresql+asyncpg://", 1)
    return url  # already has asyncpg or another async driver


def _connect_args() -> dict[str, Any]:
    args: dict[str, Any] = {}
    if settings.DB_SSL_REQUIRED:
        # Supabase pooler uses a self-signed cert in the chain; we require
        # SSL encryption but skip CA verification (no plaintext on the wire).
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        args["ssl"] = ctx
    if settings.DB_USE_PGBOUNCER:
        # PgBouncer transaction mode multiplexes connections; named prepared
        # statements are session-scoped and break across connection hops.
        args["statement_cache_size"] = 0
    return args


def _make_engine(url: str, *, testing: bool = False):
    kwargs: dict[str, Any] = {
        "echo": settings.DB_ECHO,
        "future": True,
        "connect_args": _connect_args(),
    }
    if testing:
        # NullPool prevents connection reuse across test functions
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_pre_ping=True,
            pool_recycle=3600,  # Supabase drops idle connections after ~1h
        )
    return create_async_engine(_async_url(url), **kwargs)


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
