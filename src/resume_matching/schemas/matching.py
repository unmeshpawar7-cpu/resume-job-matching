from __future__ import annotations

from datetime import datetime

from pydantic import Field

from resume_matching.domain.base import DomainModel
from resume_matching.domain.scoring.models import (
    ComponentScore,
    ExperienceFit,
    InterviewTopic,
    KnockOut,
    Recommendation,
    RoleMatch,
    SemanticDetail,
    SkillMatch,
)


class AnalyzeRequest(DomainModel):
    resume_id: str = Field(min_length=1, max_length=36)
    job_id: str = Field(min_length=1, max_length=36)
    force: bool = Field(False, description="Recompute even if a result for this version exists.")


class SkillBreakdown(DomainModel):
    matched_required: list[SkillMatch]
    missing_required: list[SkillMatch]
    matched_nice_to_have: list[SkillMatch]
    missing_nice_to_have: list[SkillMatch]


class ExplanationOut(DomainModel):
    summary: str
    strengths: list[str]
    gaps: list[str]
    source: str = Field(
        description="llm | offline_template | template_fallback | deferred_template"
    )
    provider: str
    model: str
    prompt_version: str


class MatchOut(DomainModel):
    id: str
    resume_id: str
    job_id: str
    match_percent: float
    raw_score: float
    verdict: str
    scoring_version: str
    prompt_version: str
    breakdown: list[ComponentScore]
    knockouts: list[KnockOut]
    skills: SkillBreakdown
    experience: ExperienceFit
    role_match: RoleMatch
    semantic: SemanticDetail
    recommended_improvements: list[Recommendation]
    interview_prep_topics: list[InterviewTopic]
    explanation: ExplanationOut
    created_at: datetime
    updated_at: datetime


class RankingItem(DomainModel):
    rank: int
    resume_id: str
    match_id: str
    filename: str
    current_title: str | None
    match_percent: float
    verdict: str
    required_coverage: float | None
    knockouts: list[str]
    top_reasons: list[str]


class RankingPage(DomainModel):
    job_id: str
    scoring_version: str
    candidates_considered: int
    newly_computed: int
    items: list[RankingItem]
    page: int
    page_size: int
    total_count: int
    total_pages: int
