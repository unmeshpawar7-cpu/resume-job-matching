"""Deterministic scoring engine: combines the five components into one explainable score.

``overall = sum(w_i * s_i) / sum(w_i)`` over *applicable* components (a component with no
data, e.g. a JD without nice-to-haves, is excluded and its weight redistributed), then
knock-out caps are applied. No randomness, no I/O, no LLM: the same inputs always produce
the same number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from resume_matching.core.config import ScoringSettings
from resume_matching.domain.job_analysis import JobAnalysis
from resume_matching.domain.profile import ResumeProfile
from resume_matching.domain.scoring.advice import interview_topics, recommendations
from resume_matching.domain.scoring.components import (
    coverage_score,
    experience_component,
    match_requirements,
    role_component,
    semantic_component,
)
from resume_matching.domain.scoring.models import (
    ComponentKey,
    ComponentScore,
    KnockOut,
    MatchComputation,
    SkillMatch,
    Verdict,
)
from resume_matching.domain.taxonomy import SkillTaxonomy

_LABELS: dict[ComponentKey, str] = {
    "required_skills": "Required skills",
    "nice_to_have": "Nice-to-have skills",
    "experience": "Experience",
    "role": "Role / title alignment",
    "semantic": "Semantic similarity",
}


@dataclass(frozen=True, slots=True)
class ScoringInput:
    profile: ResumeProfile
    job: JobAnalysis
    resume_text: str  # scored sections only (no header / personal sections)
    section_vectors: dict[str, Sequence[float]]
    job_vector: Sequence[float] | None
    embedding_provider: str


def verdict_for(score: float) -> Verdict:
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 45:
        return "partial"
    return "weak"


def _skills_summary(matches: list[SkillMatch]) -> str:
    full = sum(1 for m in matches if m.credit >= 1.0)
    partial = sum(1 for m in matches if 0 < m.credit < 1.0)
    text = f"{full}/{len(matches)} matched"
    return f"{text}, {partial} via related skills" if partial else text


def score_match(
    data: ScoringInput,
    taxonomy: SkillTaxonomy,
    settings: ScoringSettings,
    scoring_version: str,
) -> MatchComputation:
    required = match_requirements(
        data.job.required, data.profile, taxonomy, data.resume_text, settings
    )
    nice = match_requirements(
        data.job.nice_to_have, data.profile, taxonomy, data.resume_text, settings
    )
    exp_score, exp_fit = experience_component(data.profile, data.job, settings)
    role_score, role = role_component(data.profile, data.job, settings)
    sem_score, semantic = semantic_component(
        data.job_vector, data.section_vectors, data.embedding_provider, settings
    )

    if exp_fit.required_years is None:
        exp_summary = f"{exp_fit.candidate_years:g} years; no minimum stated"
    else:
        exp_summary = f"{exp_fit.candidate_years:g} of {exp_fit.required_years:g}+ years required"
    raw_components: list[tuple[ComponentKey, float | None, float, str, dict]] = [
        (
            "required_skills",
            coverage_score(required, settings.critical_skill_weight),
            settings.weight_required_skills,
            _skills_summary(required) if required else "No required skills identified",
            {"criticalWeight": settings.critical_skill_weight},
        ),
        (
            "nice_to_have",
            coverage_score(nice),
            settings.weight_nice_to_have,
            _skills_summary(nice) if nice else "No nice-to-have skills listed",
            {},
        ),
        (
            "experience",
            exp_score,
            settings.weight_experience,
            exp_summary,
            {"ratio": exp_fit.ratio},
        ),
        (
            "role",
            role_score,
            settings.weight_role,
            f"'{role.candidate_title or 'no title'}' vs '{role.job_title}'",
            {"titleSimilarity": role.title_similarity, "seniorityFit": role.seniority_fit},
        ),
        (
            "semantic",
            sem_score,
            settings.weight_semantic,
            f"best section: {semantic.best_section or 'n/a'} (raw cosine {semantic.raw})",
            {"raw": semantic.raw},
        ),
    ]
    applicable_weight = sum(w for _, s, w, _, _ in raw_components if s is not None) or 1.0
    components: list[ComponentScore] = []
    raw_total = 0.0
    for key, score, weight, summary, details in raw_components:
        effective = weight / applicable_weight if score is not None else 0.0
        contribution = effective * score if score is not None else 0.0
        raw_total += contribution
        components.append(
            ComponentScore(
                key=key,
                label=_LABELS[key],
                score=round(score, 1) if score is not None else None,
                weight=weight,
                effective_weight=round(effective, 4),
                contribution=round(contribution, 2),
                summary=summary,
                details=details,
            )
        )

    knockouts: list[KnockOut] = []
    missing_critical = [m.name for m in required if m.importance == "critical" and not m.matched]
    if missing_critical:
        knockouts.append(
            KnockOut(
                code="missing_critical_skill",
                message=f"Missing must-have skill(s): {', '.join(missing_critical)}",
                cap=settings.knockout_missing_critical_cap,
                skills=missing_critical,
            )
        )
    if exp_fit.ratio is not None and exp_fit.ratio < settings.knockout_experience_ratio:
        knockouts.append(
            KnockOut(
                code="insufficient_experience",
                message=(
                    f"{exp_fit.candidate_years:g} years is below "
                    f"{settings.knockout_experience_ratio:.0%} of the {exp_fit.required_years:g} "
                    "years required"
                ),
                cap=settings.knockout_experience_cap,
            )
        )
    overall = min([raw_total, *(k.cap for k in knockouts)])
    overall = round(max(0.0, min(100.0, overall)), 1)

    return MatchComputation(
        scoring_version=scoring_version,
        overall_score=overall,
        raw_score=round(raw_total, 1),
        verdict=verdict_for(overall),
        components=components,
        knockouts=knockouts,
        required_skills=required,
        nice_to_have_skills=nice,
        experience=exp_fit,
        role=role,
        semantic=semantic,
        recommendations=recommendations(required, nice, exp_fit, role, role_score),
        interview_topics=interview_topics(required, nice, exp_fit),
    )
