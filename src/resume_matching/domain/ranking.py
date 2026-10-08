"""Candidate ranking: deterministic ordering, tie-breaking and short "top reasons"."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from resume_matching.domain.scoring.models import MatchComputation


@dataclass(frozen=True, slots=True)
class RankEntry:
    resume_id: str
    created_at: datetime
    computation: MatchComputation


def _component(c: MatchComputation, key: str) -> float:
    comp = next((x for x in c.components if x.key == key), None)
    return comp.score if comp is not None and comp.score is not None else -1.0


def rank_key(entry: RankEntry) -> tuple:
    """Score desc, then required-skill coverage desc, then semantic desc, then the
    earliest-uploaded resume, then id - so equal scores always rank identically."""
    c = entry.computation
    return (
        -c.overall_score,
        -_component(c, "required_skills"),
        -_component(c, "semantic"),
        entry.created_at,
        entry.resume_id,
    )


def rank(entries: list[RankEntry], min_score: float | None = None) -> list[RankEntry]:
    kept = [e for e in entries if min_score is None or e.computation.overall_score >= min_score]
    return sorted(kept, key=rank_key)


def top_reasons(c: MatchComputation, limit: int = 3) -> list[str]:
    reasons: list[str] = []
    for k in c.knockouts:
        reasons.append(k.message)
    required = c.required_skills
    if required:
        full = sum(1 for m in required if m.credit >= 1.0)
        reasons.append(f"Matches {full}/{len(required)} required skills")
    if c.experience.required_years is not None:
        reasons.append(
            f"{c.experience.candidate_years:g} years experience vs "
            f"{c.experience.required_years:g}+ required"
        )
    if c.role.candidate_title:
        reasons.append(
            f"Title '{c.role.candidate_title}' ({c.role.title_similarity:.0%} title match)"
        )
    missing = [m.name for m in required if not m.matched]
    if missing:
        reasons.append("Missing: " + ", ".join(missing[:3]))
    return reasons[:limit]
