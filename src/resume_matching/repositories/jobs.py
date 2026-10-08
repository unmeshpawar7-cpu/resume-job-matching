from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.db.models import Job
from resume_matching.repositories.base import paginate


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def add(self, job: Job) -> Job:
        self.session.add(job)
        await self.session.flush()
        return job

    async def list_page(self, page: int, page_size: int) -> tuple[list[Job], int]:
        stmt = select(Job).order_by(Job.created_at.desc(), Job.id)
        return await paginate(self.session, stmt, page, page_size)
