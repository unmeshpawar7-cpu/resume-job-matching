from __future__ import annotations

from datetime import datetime

from resume_matching.domain.base import DomainModel
from resume_matching.domain.profile import ResumeProfile


class ResumeOut(DomainModel):
    id: str
    filename: str
    file_type: str
    content_type: str
    size_bytes: int
    page_count: int | None
    checksum: str
    owner_id: str | None
    embedding_model: str
    created_at: datetime
    profile: ResumeProfile


class ResumeSummary(DomainModel):
    id: str
    filename: str
    file_type: str
    created_at: datetime
    current_title: str | None
    seniority: str | None
    total_years: float
    top_skills: list[str]
