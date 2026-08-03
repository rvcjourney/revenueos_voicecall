"""
tests/conftest.py — Shared pytest fixtures.
Filled in progressively as models/routers are created in each phase.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base, _async_url, get_db
from app.main import app
from app.config import settings

# Separate test database — never touches production data.
# Guard against double-suffixing: pytest's own DATABASE_URL (pyproject.toml) already
# points at "/motmvoice_test", and a plain .replace("/motmvoice", "/motmvoice_test")
# would turn that into "/motmvoice_test_test" since "/motmvoice_test" also contains
# "/motmvoice" as a substring.
_raw_test_url = _async_url(settings.DATABASE_URL)
_TEST_DB_URL = (
    _raw_test_url
    if _raw_test_url.rsplit("/", 1)[-1].endswith("_test")
    else _raw_test_url.replace("/motmvoice", "/motmvoice_test")
)


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create all tables in the test DB, yield engine, then drop everything."""
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(db_engine):
    """Yield an async session bound to the test DB."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db):
    """HTTP client with get_db overridden to use the test session."""
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function")
async def fake_redis():
    """
    In-memory Redis stand-in (fakeredis + lupa for Lua/EVAL support) for tests
    that exercise Redis-based logic (app/core/concurrency.py, per-trunk slots)
    without a real Redis server. Patches app.core.redis.get_redis — every
    call site does `from app.core.redis import get_redis` at call time, so
    this patch is picked up everywhere without further wiring.
    """
    fake = FakeAsyncRedis(decode_responses=True)

    async def _get_fake_redis():
        return fake

    with patch("app.core.redis.get_redis", new=_get_fake_redis):
        yield fake
    await fake.aclose()


# Phase 2 will add:
#   - org fixture (creates an Organization row)
#   - user fixture (creates a User row + returns JWT)
#   - auth_headers fixture ({"Authorization": "Bearer <token>"})
#   - campaign fixture
