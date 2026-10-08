from __future__ import annotations

from datetime import datetime

from pydantic import Field

from resume_matching.domain.base import DomainModel
from resume_matching.domain.job_analysis import JobAnalysis


class JobCreate(DomainModel):
    title: str = Field(
        min_length=3, max_length=200, examples=["AI Backend Engineer (Python/FastAPI)"]
    )
    description: str = Field(min_length=30, max_length=20_000)
    required_skills: list[str] | None = Field(
        default=None, max_length=50, description="Explicit required skills (override text cues)."
    )
    nice_to_have_skills: list[str] | None = Field(default=None, max_length=50)
    critical_skills: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Must-have skills; a missing critical skill caps the overall score.",
    )
    min_years: float | None = Field(default=None, ge=0, le=40)


class JobOut(DomainModel):
    id: str
    title: str
    description: str
    owner_id: str | None
    created_at: datetime
    analysis: JobAnalysis


class JobSummary(DomainModel):
    id: str
    title: str
    created_at: datetime
    seniority: str | None
    min_years: float | None
    required_skills: list[str]
    nice_to_have_skills: list[str]
