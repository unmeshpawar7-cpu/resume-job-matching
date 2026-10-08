"""The five scoring components. Each is a pure function returning a 0-100 score (or
``None`` when not applicable) plus the evidence that produced it. See docs/scoring.md."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from resume_matching.core.config import ScoringSettings
from resume_matching.domain.job_analysis import JobAnalysis, SkillRequirement, literal_skill_pattern
from resume_matching.domain.profile import ResumeProfile, SkillEvidence
from resume_matching.domain.roles import seniority_fit, title_similarity
from resume_matching.domain.scoring.models import (
    ExperienceFit,
    RoleMatch,
    SemanticDetail,
    SkillMatch,
)
from resume_matching.domain.taxonomy import SkillTaxonomy


# --------------------------------------------------------------------------- skills
def match_skill(
    req: SkillRequirement,
    skills: dict[str, SkillEvidence],
    taxonomy: SkillTaxonomy,
    resume_text: str,
    related_credit: float,
) -> SkillMatch:
    base = {
        "name": req.name,
        "category": req.category,
        "importance": req.importance,
        "required_years": req.min_years,
    }
    evidence = skills.get(req.name)
    if evidence is not None:
        canonical = any(s.casefold() == req.name.casefold() for s in evidence.surface_forms)
        return SkillMatch(
            **base,
            match_type="exact" if canonical else "alias",
            credit=1.0,
            via=[] if canonical else evidence.surface_forms[:3],
            evidenced=evidence.evidenced,
            years_used=evidence.years_used,
            last_used=evidence.last_used,
        )
    if not req.in_taxonomy:
        if resume_text and literal_skill_pattern(req.name).search(resume_text):
            return SkillMatch(**base, match_type="literal", credit=1.0)
        return SkillMatch(**base, match_type="missing", credit=0.0)
    related = [skills[name] for name in sorted(taxonomy.related(req.name)) if name in skills]
    if related:
        related.sort(key=lambda e: (not e.evidenced, -e.mentions, e.name))
        return SkillMatch(
            **base,
            match_type="related",
            credit=related_credit,
            via=[e.name for e in related[:3]],
            evidenced=related[0].evidenced,
        )
    return SkillMatch(**base, match_type="missing", credit=0.0)


def coverage_score(matches: Sequence[SkillMatch], critical_weight: float = 1.0) -> float | None:
    if not matches:
        return None
    weights = [critical_weight if m.importance == "critical" else 1.0 for m in matches]
    earned = sum(w * m.credit for w, m in zip(weights, matches, strict=True))
    return 100.0 * earned / sum(weights)


def match_requirements(
    requirements: Iterable[SkillRequirement],
    profile: ResumeProfile,
    taxonomy: SkillTaxonomy,
    resume_text: str,
    settings: ScoringSettings,
) -> list[SkillMatch]:
    skills = profile.skill_map()
    return [
        match_skill(r, skills, taxonomy, resume_text, settings.related_skill_credit)
        for r in requirements
    ]


# --------------------------------------------------------------------------- experience
def experience_curve(ratio: float, settings: ScoringSettings) -> float:
    """Piecewise-linear curve of ``candidate_years / required_years``.

    ``0 -> 0``, ``0.5 -> half_score``, ``1.0 -> meets_score``, then
    ``+overqualified_slope`` per extra multiple of the requirement, capped at 100.
    More experience never lowers the score (over-qualification penalties act as an age proxy).
    """
    half, meets = settings.experience_half_score, settings.experience_meets_score
    if ratio <= 0:
        return 0.0
    if ratio < 0.5:
        return half * ratio / 0.5
    if ratio < 1.0:
        return half + (meets - half) * (ratio - 0.5) / 0.5
    return min(100.0, meets + settings.experience_overqualified_slope * (ratio - 1.0))


def experience_component(
    profile: ResumeProfile, job: JobAnalysis, settings: ScoringSettings
) -> tuple[float | None, ExperienceFit]:
    years = profile.experience.total_years
    fit = ExperienceFit(
        candidate_years=years,
        required_years=job.min_years,
        ratio=None,
        source=profile.experience.source,
        positions=len(profile.experience.positions),
    )
    if job.min_years is None:
        return None, fit
    if job.min_years <= 0:
        return 100.0, fit
    fit.ratio = round(years / job.min_years, 3)
    return experience_curve(years / job.min_years, settings), fit


# --------------------------------------------------------------------------- role
def role_component(
    profile: ResumeProfile, job: JobAnalysis, settings: ScoringSettings
) -> tuple[float | None, RoleMatch]:
    best_title, best_sim = None, 0.0
    for title in profile.titles[:5]:
        sim = title_similarity(title, job.title)
        if best_title is None or sim > best_sim:
            best_title, best_sim = title, sim
    best_title = best_title or profile.current_title
    fit = seniority_fit(profile.seniority, job.seniority)
    role = RoleMatch(
        candidate_title=best_title,
        job_title=job.title,
        title_similarity=round(best_sim, 4),
        candidate_seniority=profile.seniority,
        job_seniority=job.seniority,
        seniority_fit=fit,
        candidate_families=profile.role_families,
        job_families=job.role_families,
    )
    if not job.title.strip():
        return None, role
    if fit is None:
        return 100.0 * best_sim, role
    w = settings.role_title_weight
    return 100.0 * (w * best_sim + (1 - w) * fit), role


# --------------------------------------------------------------------------- semantic
def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if va.shape != vb.shape:
        raise ValueError(f"Embedding dimension mismatch: {va.shape} vs {vb.shape}")
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def calibration(provider: str, settings: ScoringSettings) -> tuple[float, float]:
    if provider == "openai":
        return settings.semantic_floor_openai, settings.semantic_ceiling_openai
    return settings.semantic_floor_hashing, settings.semantic_ceiling_hashing


def semantic_component(
    job_vector: Sequence[float] | None,
    section_vectors: dict[str, Sequence[float]],
    provider: str,
    settings: ScoringSettings,
) -> tuple[float | None, SemanticDetail]:
    floor, ceiling = calibration(provider, settings)
    detail = SemanticDetail(
        provider=provider,
        section_similarity={},
        best_section=None,
        raw=None,
        floor=floor,
        ceiling=ceiling,
    )
    if job_vector is None or not section_vectors:
        return None, detail
    sims = {
        name: round(cosine(job_vector, vec), 4) for name, vec in sorted(section_vectors.items())
    }
    best = max(sims, key=lambda k: (sims[k], k))
    w = settings.semantic_max_weight
    raw = w * max(sims.values()) + (1 - w) * (sum(sims.values()) / len(sims))
    detail.section_similarity = sims
    detail.best_section = best
    detail.raw = round(raw, 4)
    scaled = (raw - floor) / (ceiling - floor) if ceiling > floor else 0.0
    return 100.0 * min(1.0, max(0.0, scaled)), detail
