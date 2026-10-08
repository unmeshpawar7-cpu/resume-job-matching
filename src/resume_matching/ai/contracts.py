"""Contracts between the scoring engine and the LLM.

* :class:`ExplanationFacts` - the ONLY input the LLM sees: computed numbers, skill names
  and recommendation texts. No resume text, no names or contact details.
* :class:`MatchExplanation` - the structured output the LLM must return; validated with
  Pydantic and then checked for grounding (see :mod:`resume_matching.ai.explanation`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from resume_matching.domain.base import DomainModel
from resume_matching.domain.scoring.models import MatchComputation
from resume_matching.domain.taxonomy import SkillTaxonomy

ExplanationSource = Literal["llm", "offline_template", "template_fallback", "deferred_template"]


class ComponentFact(DomainModel):
    key: str
    label: str
    score: float | None
    summary: str


class RelatedFact(DomainModel):
    skill: str
    via: list[str]


class ExplanationFacts(DomainModel):
    job_title: str
    candidate_title: str | None
    overall_score: float
    verdict: str
    components: list[ComponentFact]
    required_matched: list[str]
    required_missing: list[str]
    critical_missing: list[str]
    related_matches: list[RelatedFact]
    nice_matched: list[str]
    nice_missing: list[str]
    candidate_years: float
    required_years: float | None
    knockouts: list[str]
    recommendations: list[str]
    allowed_skills: list[str]


class MatchExplanation(DomainModel):
    summary: str = Field(min_length=20, max_length=1200)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list, max_length=5)
    skills_mentioned: list[str] = Field(default_factory=list, max_length=40)


def build_facts(c: MatchComputation, taxonomy: SkillTaxonomy) -> ExplanationFacts:
    required_matched = [m.name for m in c.required_skills if m.credit >= 1.0]
    allowed = set(c.skill_names())
    allowed |= taxonomy.find_names(c.role.job_title)
    if c.role.candidate_title:
        allowed |= taxonomy.find_names(c.role.candidate_title)
    return ExplanationFacts(
        job_title=c.role.job_title,
        candidate_title=c.role.candidate_title,
        overall_score=c.overall_score,
        verdict=c.verdict,
        components=[
            ComponentFact(key=x.key, label=x.label, score=x.score, summary=x.summary)
            for x in c.components
        ],
        required_matched=required_matched,
        required_missing=[m.name for m in c.required_skills if not m.matched],
        critical_missing=[
            m.name for m in c.required_skills if m.importance == "critical" and not m.matched
        ],
        related_matches=[
            RelatedFact(skill=m.name, via=m.via)
            for m in c.required_skills
            if m.match_type == "related"
        ],
        nice_matched=[m.name for m in c.nice_to_have_skills if m.matched],
        nice_missing=[m.name for m in c.nice_to_have_skills if not m.matched],
        candidate_years=c.experience.candidate_years,
        required_years=c.experience.required_years,
        knockouts=[k.message for k in c.knockouts],
        recommendations=[r.message for r in c.recommendations],
        allowed_skills=sorted(allowed),
    )
