"""Async engine / session factory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from resume_matching.db.models import Base


def create_engine(url: str, echo: bool = False) -> AsyncEngine:
    kwargs: dict[str, Any] = {"echo": echo}
    if url.startswith("sqlite"):
        if ":memory:" in url or url.endswith("://"):
            kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        engine = create_async_engine(url, **kwargs)

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_async_engine(url, pool_pre_ping=True, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
