from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.core.errors import NotFoundError
from resume_matching.db.models import Job, User
from resume_matching.domain.job_analysis import analyze_job
from resume_matching.repositories.jobs import JobRepository
from resume_matching.schemas.jobs import JobCreate
from resume_matching.services.container import AppContainer
from resume_matching.services.resume_service import embedding_input

logger = logging.getLogger(__name__)


def job_embedding_text(title: str, description: str) -> str:
    return embedding_input(f"{title}\n{description}")


class JobService:
    def __init__(self, session: AsyncSession, container: AppContainer) -> None:
        self.session = session
        self.c = container
        self.repo = JobRepository(session)

    async def create(self, body: JobCreate, user: User) -> Job:
        analysis = analyze_job(
            title=body.title,
            description=body.description,
            taxonomy=self.c.taxonomy,
            required_skills=body.required_skills,
            nice_to_have_skills=body.nice_to_have_skills,
            critical_skills=body.critical_skills,
            min_years=body.min_years,
        )
        [vector] = await self.c.embedder.embed([job_embedding_text(body.title, body.description)])
        job = await self.repo.add(
            Job(
                owner_id=user.id,
                title=body.title.strip(),
                description=body.description,
                request=body.model_dump(
                    mode="json", by_alias=True, exclude={"title", "description"}
                ),
                analysis=analysis.to_json_dict(),
                embedding=vector,
                embedding_model=self.c.embedder.model_id,
            )
        )
        await self.session.commit()
        logger.info(
            "job_created", extra={"job_id": job.id, "requirements": len(analysis.requirements)}
        )
        return job

    async def get(self, job_id: str) -> Job:
        job = await self.repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    async def list(self, page: int, page_size: int) -> tuple[list[Job], int]:
        return await self.repo.list_page(page, page_size)
