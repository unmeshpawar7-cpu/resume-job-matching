"""Resume upload: validate -> extract text -> (redact) -> parse profile -> embed sections."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from resume_matching.core.errors import ConflictError, FieldError, ForbiddenError, NotFoundError
from resume_matching.core.redaction import mask_years, redact_pii
from resume_matching.db.models import Resume, ResumeSection, User
from resume_matching.domain.profile import PARSER_VERSION, build_profile
from resume_matching.parsing.extractors import extract_document
from resume_matching.repositories.resumes import ResumeRepository
from resume_matching.services.container import AppContainer

logger = logging.getLogger(__name__)


def embedding_input(text: str) -> str:
    """What is sent to the embedding provider: PII-redacted, years masked."""
    return mask_years(redact_pii(text))


class ResumeService:
    def __init__(self, session: AsyncSession, container: AppContainer) -> None:
        self.session = session
        self.c = container
        self.repo = ResumeRepository(session)

    async def upload(self, filename: str, data: bytes, user: User) -> Resume:
        settings = self.c.settings
        doc = await run_in_threadpool(
            extract_document,
            filename,
            data,
            max_pdf_pages=settings.max_pdf_pages,
            max_docx_uncompressed_bytes=settings.max_docx_uncompressed_bytes,
        )
        existing = await self.repo.get_by_checksum(doc.checksum)
        if existing is not None:
            raise ConflictError(
                f"This file was already uploaded as resume {existing.id}",
                errors=[FieldError("file", f"duplicate of resume {existing.id}")],
            )
        text = redact_pii(doc.text) if settings.redact_analysis_payloads else doc.text
        profile, sections = build_profile(text, self.c.taxonomy, self.c.today())
        scored = sections.scored()
        vectors = await self.c.embedder.embed([embedding_input(t) for t in scored.values()])
        resume = Resume(
            owner_id=user.id,
            filename=filename[:255],
            file_type=doc.file_type,
            content_type=doc.content_type,
            size_bytes=doc.size_bytes,
            page_count=doc.page_count,
            checksum=doc.checksum,
            text=text,
            profile=profile.to_json_dict(),
            parser_version=PARSER_VERSION,
            taxonomy_version=self.c.taxonomy.version,
            embedding_model=self.c.embedder.model_id,
        )
        resume.sections = [
            ResumeSection(section_type=name, position=i, text=body, embedding=vec)
            for i, ((name, body), vec) in enumerate(zip(scored.items(), vectors, strict=True))
        ]
        await self.repo.add(resume)
        await self.c.vector_store.upsert(
            self.session, resume.id, {s.section_type: s.embedding or [] for s in resume.sections}
        )
        await self.session.commit()
        logger.info(
            "resume_uploaded",
            extra={
                "resume_id": resume.id,
                "file_type": doc.file_type,
                "size_bytes": doc.size_bytes,
                "skills": len(profile.skills),
            },
        )
        return resume

    async def get(self, resume_id: str) -> Resume:
        resume = await self.repo.get(resume_id)
        if resume is None:
            raise NotFoundError(f"Resume {resume_id} not found")
        return resume

    async def list(self, page: int, page_size: int) -> tuple[list[Resume], int]:
        return await self.repo.list_page(page, page_size)

    async def delete(self, resume_id: str, user: User) -> None:
        resume = await self.get(resume_id)
        if user.role != "admin" and resume.owner_id != user.id:
            raise ForbiddenError("Only the uploader or an admin can delete this resume")
        await self.repo.delete(resume)
        await self.c.vector_store.delete(self.session, resume_id)
        await self.session.commit()
        logger.info("resume_deleted", extra={"resume_id": resume_id})
