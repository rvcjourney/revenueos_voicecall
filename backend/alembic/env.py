"""
alembic/env.py — Async-aware Alembic migration environment.
DATABASE_URL comes from app.config.settings (never from alembic.ini).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base, _async_url, _connect_args

# Load Alembic's logging config from alembic.ini
alembic_config = context.config
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Import all models so their tables are registered in Base.metadata.
# Add imports here as model files are created.
import app.models  # noqa: F401  — activates any uncommented imports in models/__init__.py

target_metadata = Base.metadata

# Objects that exist in the live DB but can never be expressed in the ORM,
# so autogenerate would otherwise propose dropping them on every run.
# Add an entry here (rather than hand-editing the generated migration) whenever
# a functional/expression index or similar unmappable object is introduced.
_AUTOGENERATE_IGNORE = {
    ("index", "ix_call_transcripts_full_text_gin"),  # functional GIN index, see migration 0001
}


def _include_object(object, name, type_, reflected, compare_to) -> bool:
    return (type_, name) not in _AUTOGENERATE_IGNORE


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    context.configure(
        url=_async_url(settings.DATABASE_URL),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Render ENUMs as native Postgres ENUM types
        render_as_batch=False,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_async_engine(
        _async_url(settings.DATABASE_URL),
        echo=False,
        connect_args=_connect_args(),
    )
    async with engine.connect() as conn:
        await conn.run_sync(_run_sync_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
