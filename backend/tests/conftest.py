"""
tests/conftest.py — Shared pytest fixtures.
Filled in progressively as models/routers are created in each phase.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base, _async_url, get_db
from app.main import app
from app.config import settings

# Separate test database — never touches production data
_TEST_DB_URL = _async_url(settings.DATABASE_URL).replace(
    "/motmvoice", "/motmvoice_test"
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

# Phase 2 will add:
#   - org fixture (creates an Organization row)
#   - user fixture (creates a User row + returns JWT)
#   - auth_headers fixture ({"Authorization": "Bearer <token>"})
#   - campaign fixture
