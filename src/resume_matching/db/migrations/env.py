"""Alembic environment (async). URL from ``DATABASE_URL`` / settings."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection

from resume_matching.core.config import get_settings
from resume_matching.db.models import Base
from resume_matching.db.session import create_engine

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or os.environ.get(
        "DATABASE_URL", get_settings().database_url
    )


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
