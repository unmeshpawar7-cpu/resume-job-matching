"""Deterministic template narrative built from :class:`ExplanationFacts`.

Used by the ``offline`` LLM provider, as the fallback whenever an LLM response fails
validation or grounding, and for matches batch-computed during ranking. It only ever
restates facts, so it is grounded by construction.
"""

from __future__ import annotations

from resume_matching.ai.contracts import ExplanationFacts, MatchExplanation

_VERDICT_TEXT = {
    "strong": "a strong match",
    "good": "a good match",
    "partial": "a partial match",
    "weak": "a weak match",
}


def _list(names: list[str], limit: int = 5) -> str:
    shown = names[:limit]
    if len(names) > limit:
        return ", ".join(shown) + f" and {len(names) - limit} more"
    if len(shown) <= 1:
        return "".join(shown)
    return ", ".join(shown[:-1]) + " and " + shown[-1]


def render_explanation(facts: ExplanationFacts) -> MatchExplanation:
    total_required = (
        len(facts.required_matched) + len(facts.required_missing) + len(facts.related_matches)
    )
    sentences = [
        f"Scored {facts.overall_score:g}/100 for '{facts.job_title}': "
        f"{_VERDICT_TEXT[facts.verdict]}."
    ]
    if total_required:
        sentences.append(
            f"The resume covers {len(facts.required_matched)} of {total_required} required "
            "skills"
            + (
                f", with partial credit for {len(facts.related_matches)} via related skills."
                if facts.related_matches
                else "."
            )
        )
    if facts.required_years is not None:
        sentences.append(
            f"Dated experience totals {facts.candidate_years:g} years against "
            f"{facts.required_years:g}+ required."
        )
    if facts.knockouts:
        sentences.append("Score capped: " + "; ".join(facts.knockouts) + ".")

    strengths: list[str] = []
    if facts.required_matched:
        strengths.append(f"Required skills present: {_list(facts.required_matched)}.")
    if facts.nice_matched:
        strengths.append(f"Nice-to-have skills present: {_list(facts.nice_matched)}.")
    if facts.required_years is not None and facts.candidate_years >= facts.required_years:
        strengths.append("Meets the stated experience requirement.")
    best = max(
        (c for c in facts.components if c.score is not None),
        key=lambda c: (c.score or 0, c.key),
        default=None,
    )
    if best is not None and len(strengths) < 5:
        strengths.append(f"Strongest component: {best.label} ({best.score:g}/100).")

    gaps: list[str] = []
    if facts.critical_missing:
        gaps.append(f"Missing must-have skills: {_list(facts.critical_missing)}.")
    other_missing = [s for s in facts.required_missing if s not in facts.critical_missing]
    if other_missing:
        gaps.append(f"Missing required skills: {_list(other_missing)}.")
    for rel in facts.related_matches[:2]:
        gaps.append(f"{rel.skill} only indirectly covered by {_list(rel.via, 2)}.")
    if facts.required_years is not None and facts.candidate_years < facts.required_years:
        gaps.append("Below the stated minimum years of experience.")
    if facts.nice_missing and len(gaps) < 5:
        gaps.append(f"Missing nice-to-haves: {_list(facts.nice_missing, 3)}.")

    mentioned = [
        *facts.required_matched,
        *facts.nice_matched,
        *facts.critical_missing,
        *other_missing,
        *(s for r in facts.related_matches[:2] for s in [r.skill, *r.via[:2]]),
        *facts.nice_missing[:3],
    ]
    return MatchExplanation(
        summary=" ".join(sentences),
        strengths=strengths[:5],
        gaps=gaps[:5],
        skills_mentioned=list(dict.fromkeys(mentioned)),
    )
