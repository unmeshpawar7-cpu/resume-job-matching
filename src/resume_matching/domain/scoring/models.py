"""Result models of the scoring engine (persisted as JSON in ``match_results.result``)."""

from __future__ import annotations

from typing import Any, Literal

from resume_matching.domain.base import DomainModel

ComponentKey = Literal["required_skills", "nice_to_have", "experience", "role", "semantic"]
MatchType = Literal["exact", "alias", "related", "literal", "missing"]
Verdict = Literal["strong", "good", "partial", "weak"]


class SkillMatch(DomainModel):
    name: str
    category: str
    importance: Literal["critical", "required", "nice_to_have"]
    match_type: MatchType
    credit: float
    via: list[str] = []  # related skills that earned partial credit / surface aliases
    evidenced: bool = False  # used in experience/projects, not only listed
    years_used: float | None = None
    last_used: str | None = None
    required_years: float | None = None

    @property
    def matched(self) -> bool:
        return self.match_type != "missing"


class ComponentScore(DomainModel):
    key: ComponentKey
    label: str
    score: float | None  # None = not applicable (its weight is redistributed)
    weight: float
    effective_weight: float
    contribution: float
    summary: str
    details: dict[str, Any] = {}


class KnockOut(DomainModel):
    code: Literal["missing_critical_skill", "insufficient_experience"]
    message: str
    cap: float
    skills: list[str] = []


class ExperienceFit(DomainModel):
    candidate_years: float
    required_years: float | None
    ratio: float | None
    source: str
    positions: int


class RoleMatch(DomainModel):
    candidate_title: str | None
    job_title: str
    title_similarity: float
    candidate_seniority: str | None
    job_seniority: str | None
    seniority_fit: float | None
    candidate_families: list[str]
    job_families: list[str]


class SemanticDetail(DomainModel):
    provider: str
    section_similarity: dict[str, float]
    best_section: str | None
    raw: float | None
    floor: float
    ceiling: float


class Recommendation(DomainModel):
    code: str
    priority: Literal["high", "medium", "low"]
    message: str
    skills: list[str] = []


class InterviewTopic(DomainModel):
    topic: str
    reason: str
    skills: list[str] = []


class MatchComputation(DomainModel):
    scoring_version: str
    overall_score: float
    raw_score: float
    verdict: Verdict
    components: list[ComponentScore]
    knockouts: list[KnockOut]
    required_skills: list[SkillMatch]
    nice_to_have_skills: list[SkillMatch]
    experience: ExperienceFit
    role: RoleMatch
    semantic: SemanticDetail
    recommendations: list[Recommendation]
    interview_topics: list[InterviewTopic]

    def component(self, key: ComponentKey) -> ComponentScore:
        return next(c for c in self.components if c.key == key)

    def skill_names(self) -> set[str]:
        """Every skill name the result talks about (used for explanation grounding)."""
        names: set[str] = set()
        for match in [*self.required_skills, *self.nice_to_have_skills]:
            names.add(match.name)
            names.update(match.via)
        return names
