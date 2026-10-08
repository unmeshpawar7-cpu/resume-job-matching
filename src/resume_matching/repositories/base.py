"""Shared repository helpers."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def paginate(
    session: AsyncSession, stmt: Select[Any], page: int, page_size: int
) -> tuple[list[Any], int]:
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = (await session.scalars(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return list(rows), int(total or 0)
