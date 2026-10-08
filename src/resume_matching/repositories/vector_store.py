"""Vector store abstraction for candidate retrieval.

Section embeddings are always persisted in ``resume_sections.embedding``. The vector store
answers "which resumes are semantically closest to this job?" and is used by ranking to
pre-select a candidate pool when there are more resumes than ``RANKING_CANDIDATE_POOL``.

* :class:`PgVectorStore` - production: cosine-distance query served by the HNSW index.
* :class:`InMemoryVectorStore` - tests / SQLite: numpy cosine over vectors held in memory,
  hydrated from the database on startup.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np
from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.db.models import ResumeSection


class VectorStore(Protocol):
    async def upsert(
        self, session: AsyncSession, resume_id: str, vectors: dict[str, Sequence[float]]
    ) -> None: ...

    async def delete(self, session: AsyncSession, resume_id: str) -> None: ...

    async def search(
        self, session: AsyncSession, query: Sequence[float], limit: int
    ) -> list[tuple[str, float]]:
        """Return ``(resume_id, best_section_cosine)`` for the closest resumes, best first."""
        ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vectors: dict[tuple[str, str], np.ndarray] = {}

    def __len__(self) -> int:
        return len(self._vectors)

    def load(self, rows: Sequence[tuple[str, str, Sequence[float]]]) -> None:
        for resume_id, section, vector in rows:
            self._put(resume_id, section, vector)

    def _put(self, resume_id: str, section: str, vector: Sequence[float]) -> None:
        arr = np.asarray(vector, dtype=np.float64)
        norm = np.linalg.norm(arr)
        self._vectors[(resume_id, section)] = arr / norm if norm else arr

    async def upsert(
        self, session: AsyncSession, resume_id: str, vectors: dict[str, Sequence[float]]
    ) -> None:
        await self.delete(session, resume_id)
        for section, vector in vectors.items():
            self._put(resume_id, section, vector)

    async def delete(self, session: AsyncSession, resume_id: str) -> None:
        for key in [k for k in self._vectors if k[0] == resume_id]:
            del self._vectors[key]

    async def search(
        self, session: AsyncSession, query: Sequence[float], limit: int
    ) -> list[tuple[str, float]]:
        if not self._vectors:
            return []
        q = np.asarray(query, dtype=np.float64)
        q = q / (np.linalg.norm(q) or 1.0)
        keys = list(self._vectors)
        sims = np.stack([self._vectors[k] for k in keys]) @ q
        best: dict[str, float] = {}
        for (resume_id, _), sim in zip(keys, sims, strict=True):
            best[resume_id] = max(best.get(resume_id, -1.0), float(sim))
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]


class PgVectorStore:
    """Uses the ``embedding`` column written by the ORM; upsert/delete are no-ops because
    the rows themselves are the index (deletes cascade from ``resumes``)."""

    #: Over-fetch sections so that ``limit`` distinct resumes survive de-duplication.
    overfetch = 4

    async def upsert(
        self, session: AsyncSession, resume_id: str, vectors: dict[str, Sequence[float]]
    ) -> None:
        return None

    async def delete(self, session: AsyncSession, resume_id: str) -> None:
        return None

    async def search(
        self, session: AsyncSession, query: Sequence[float], limit: int
    ) -> list[tuple[str, float]]:
        # pgvector cosine-distance operator; served by the HNSW index (vector_cosine_ops).
        distance = ResumeSection.embedding.op("<=>", return_type=Float())(list(query))
        stmt = (
            select(ResumeSection.resume_id, (1 - distance).label("similarity"))
            .where(ResumeSection.embedding.is_not(None))
            .order_by(distance)
            .limit(limit * self.overfetch)
        )
        best: dict[str, float] = {}
        for resume_id, similarity in (await session.execute(stmt)).all():
            best.setdefault(resume_id, float(similarity))
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
