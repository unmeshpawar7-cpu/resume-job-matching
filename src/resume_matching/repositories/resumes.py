from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from resume_matching.db.models import Resume, ResumeSection
from resume_matching.repositories.base import paginate


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, resume_id: str, *, with_sections: bool = False) -> Resume | None:
        if not with_sections:
            return await self.session.get(Resume, resume_id)
        stmt = select(Resume).where(Resume.id == resume_id).options(selectinload(Resume.sections))
        return await self.session.scalar(stmt)

    async def get_by_checksum(self, checksum: str) -> Resume | None:
        return await self.session.scalar(select(Resume).where(Resume.checksum == checksum))

    async def add(self, resume: Resume) -> Resume:
        self.session.add(resume)
        await self.session.flush()
        return resume

    async def list_page(self, page: int, page_size: int) -> tuple[list[Resume], int]:
        stmt = select(Resume).order_by(Resume.created_at.desc(), Resume.id)
        return await paginate(self.session, stmt, page, page_size)

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(Resume.id))) or 0)

    async def list_with_sections(self, ids: list[str] | None = None) -> list[Resume]:
        stmt = select(Resume).options(selectinload(Resume.sections)).order_by(Resume.created_at)
        if ids is not None:
            stmt = stmt.where(Resume.id.in_(ids))
        return list((await self.session.scalars(stmt)).all())

    async def all_section_vectors(self) -> list[tuple[str, str, list[float]]]:
        stmt = select(ResumeSection.resume_id, ResumeSection.section_type, ResumeSection.embedding)
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1], r[2]) for r in rows if r[2] is not None]

    async def delete(self, resume: Resume) -> None:
        # Explicit statement so the database-level ON DELETE CASCADE removes sections and
        # match results in one round trip (the ORM relationship uses passive_deletes).
        await self.session.execute(delete(Resume).where(Resume.id == resume.id))
