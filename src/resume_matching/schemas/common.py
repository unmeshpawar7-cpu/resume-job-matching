"""API envelope and pagination DTOs (camelCase on the wire)."""

from __future__ import annotations

import math
from typing import Generic, TypeVar

from pydantic import Field

from resume_matching.domain.base import DomainModel

T = TypeVar("T")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class Envelope(DomainModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None


class ErrorItem(DomainModel):
    field: str
    message: str


class ErrorEnvelope(DomainModel):
    success: bool = False
    message: str
    errors: list[ErrorItem] = Field(default_factory=list)
    trace_id: str


class Page(DomainModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total_count: int
    total_pages: int

    @classmethod
    def build(cls, items: list[T], page: int, page_size: int, total: int) -> Page[T]:
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_count=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )


def ok(data: object, message: str | None = None) -> dict:
    """Serialise a success envelope (camelCase)."""
    if isinstance(data, DomainModel):
        data = data.to_json_dict()
    return {"success": True, "data": data, "message": message}
