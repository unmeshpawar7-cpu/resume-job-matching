"""Deterministic recommended improvements and interview-prep topics.

Generated from the computed matches only - no LLM involved - so they are reproducible and
always consistent with the score.
"""

from __future__ import annotations

from resume_matching.domain.scoring.models import (
    ExperienceFit,
    InterviewTopic,
    Recommendation,
    RoleMatch,
    SkillMatch,
)

MAX_RECOMMENDATIONS = 6
MAX_TOPICS = 6


def _join(names: list[str], limit: int = 4) -> str:
    shown = names[:limit]
    more = len(names) - len(shown)
    text = ", ".join(shown)
    return f"{text} (+{more} more)" if more > 0 else text


def recommendations(
    required: list[SkillMatch],
    nice: list[SkillMatch],
    experience: ExperienceFit,
    role: RoleMatch,
    role_score: float | None,
) -> list[Recommendation]:
    recs: list[Recommendation] = []
    missing_critical = [m.name for m in required if m.importance == "critical" and not m.matched]
    missing_required = [m.name for m in required if m.importance == "required" and not m.matched]
    related = [m for m in required if m.match_type == "related"]
    unevidenced = [
        m.name for m in required if m.match_type in ("exact", "alias") and not m.evidenced
    ]
    years_short = [
        m.name
        for m in required
        if m.matched and m.required_years and (m.years_used or 0) < m.required_years
    ]
    missing_nice = [m.name for m in nice if not m.matched]

    if missing_critical:
        recs.append(Recommendation(
            code="missing_critical_skills", priority="high", skills=missing_critical,
            message=f"Must-have skills not found in the resume: {_join(missing_critical)}. "
            "If you have this experience, state it explicitly with a concrete project.",
        ))  # fmt: skip
    if missing_required:
        recs.append(Recommendation(
            code="missing_required_skills", priority="high", skills=missing_required,
            message=f"Required skills not found: {_join(missing_required)}. Add them where you "
            "have used them, or plan to close the gap.",
        ))  # fmt: skip
    for m in related[:2]:
        recs.append(Recommendation(
            code="transferable_skill", priority="medium", skills=[m.name, *m.via],
            message=f"{m.name} is required; the resume shows the related {_join(m.via, 2)}. "
            f"Describe comparable work to make the transfer to {m.name} explicit.",
        ))  # fmt: skip
    if unevidenced:
        recs.append(Recommendation(
            code="add_evidence", priority="medium", skills=unevidenced,
            message=f"{_join(unevidenced)} appear only in a skills list. Add experience or "
            "project bullets that show how they were used.",
        ))  # fmt: skip
    if years_short:
        recs.append(Recommendation(
            code="skill_years", priority="medium", skills=years_short,
            message=f"The role asks for specific years with {_join(years_short)}; make the "
            "duration of that work visible in the dated experience entries.",
        ))  # fmt: skip
    if experience.ratio is not None and experience.ratio < 1.0:
        recs.append(Recommendation(
            code="experience_gap", priority="medium",
            message=f"The role asks for {experience.required_years:g}+ years; the dated "
            f"experience totals {experience.candidate_years:g} years. Include all relevant "
            "positions with start and end dates.",
        ))  # fmt: skip
    if role_score is not None and role_score < 50:
        recs.append(Recommendation(
            code="role_alignment", priority="low",
            message=f"No previous title closely matches '{role.job_title}'. If your work "
            "overlapped this role, reflect it in the summary.",
        ))  # fmt: skip
    if missing_nice:
        recs.append(Recommendation(
            code="nice_to_have", priority="low", skills=missing_nice[:4],
            message=f"Nice-to-have skills that would strengthen the match: {_join(missing_nice)}.",
        ))  # fmt: skip
    return recs[:MAX_RECOMMENDATIONS]


def interview_topics(
    required: list[SkillMatch], nice: list[SkillMatch], experience: ExperienceFit
) -> list[InterviewTopic]:
    topics: list[InterviewTopic] = []
    strong = sorted(
        (m for m in required if m.match_type in ("exact", "alias") and m.evidenced),
        key=lambda m: (m.importance != "critical", -(m.years_used or 0), m.name),
    )
    for m in strong[:3]:
        topics.append(InterviewTopic(
            topic=f"{m.name} in production",
            reason="Evidenced in the experience section; probe depth, trade-offs and ownership.",
            skills=[m.name],
        ))  # fmt: skip
    for m in [m for m in required if m.match_type == "related"][:2]:
        topics.append(InterviewTopic(
            topic=f"Transfer from {m.via[0]} to {m.name}",
            reason=f"Only the related skill {m.via[0]} was found; assess how quickly it transfers.",
            skills=[m.name, m.via[0]],
        ))  # fmt: skip
    for m in [m for m in required if not m.matched][:2]:
        topics.append(InterviewTopic(
            topic=f"{m.name} fundamentals",
            reason=f"{m.name} is {m.importance.replace('_', ' ')} but not on the resume.",
            skills=[m.name],
        ))  # fmt: skip
    unevidenced = [
        m.name for m in required if m.match_type in ("exact", "alias") and not m.evidenced
    ]
    if unevidenced:
        topics.append(InterviewTopic(
            topic="Hands-on usage of listed skills",
            reason="Listed without supporting experience bullets.",
            skills=unevidenced[:3],
        ))  # fmt: skip
    if experience.ratio is not None and experience.ratio < 1.0:
        topics.append(InterviewTopic(
            topic="Scope and ownership of past work",
            reason="Dated experience is below the stated minimum; assess the depth of impact.",
        ))  # fmt: skip
    if not topics and nice:
        topics.append(InterviewTopic(
            topic="Nice-to-have areas",
            reason="Explore familiarity with the optional parts of the stack.",
            skills=[m.name for m in nice[:3]],
        ))  # fmt: skip
    return topics[:MAX_TOPICS]
