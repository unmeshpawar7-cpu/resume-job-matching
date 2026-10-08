"""Job-description analysis: required vs nice-to-have skills, minimum years, title.

Classification rules (documented in docs/scoring.md):

1. Skills passed explicitly in the request win for the skills they name.
2. In the text, each skill occurrence is classified by the *cue* of its clause
   (``must have`` -> critical, ``required`` -> required, ``nice to have``/``bonus``/``a plus``/
   ``preferred`` -> nice-to-have), else by the cue of the current block heading
   (``Requirements:``, ``Nice to have:``), else it is an un-cued *mention*.
3. Across occurrences: critical > required > nice-to-have > mention.
4. Un-cued mentions are treated as required: if a JD names a technology without hedging it,
   assume it matters.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from resume_matching.domain.base import DomainModel
from resume_matching.domain.roles import detect_seniority, role_families, seniority_from_years
from resume_matching.domain.taxonomy import (
    LEFT_BOUNDARY,
    RIGHT_BOUNDARY,
    SkillTaxonomy,
    alias_pattern,
)

ANALYZER_VERSION = "1.0.0"
Importance = Literal["critical", "required", "nice_to_have"]
Cue = Literal["critical", "required", "nice"]

_NICE_CUES = (
    r"nice[\s-]to[\s-]haves?",
    r"good[\s-]to[\s-]have",
    r"\bbonus(?:\s+points)?\b",
    r"\ba\s+plus\b",
    r"\bis\s+a\s+plus\b",
    r"\bplus\b",
    r"\bpreferred\b",
    r"\bdesirable\b",
    r"\bdesired\b",
    r"would\s+be\s+(?:great|nice|helpful)",
    r"\bideally\b",
    r"\boptional\b",
    r"not\s+required",
)
_CRITICAL_CUES = (
    r"must[\s-]haves?",
    r"\bmandatory\b",
    r"non[\s-]negotiable",
    r"\byou\s+must\b",
    r"\bmust\b",
)
_REQUIRED_CUES = (
    r"\brequired\b",
    r"\brequirements?\b",
    r"minimum\s+qualifications",
    r"basic\s+qualifications",
    r"\bqualifications\b",
    r"what\s+you(?:'ll|\s+will)\s+need",
    r"what\s+we(?:'re|\s+are)\s+looking\s+for",
    r"\byou\s+(?:have|bring)\b",
)
_CUE_RES: list[tuple[Cue, re.Pattern[str]]] = [
    ("nice", re.compile("|".join(_NICE_CUES), re.IGNORECASE)),
    ("critical", re.compile("|".join(_CRITICAL_CUES), re.IGNORECASE)),
    ("required", re.compile("|".join(_REQUIRED_CUES), re.IGNORECASE)),
]
_RANK: dict[str, int] = {"critical": 3, "required": 2, "nice": 1, "mention": 0}
_YEARS_RE = re.compile(
    r"(?P<n>\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r";|(?<=[a-z0-9)])\.\s+(?=[A-Z])|\.$")


class SkillRequirement(DomainModel):
    name: str
    category: str
    importance: Importance
    source: Literal["explicit", "cue", "mentioned"]
    in_taxonomy: bool = True
    min_years: float | None = None
    mentions: int = 0


class JobAnalysis(DomainModel):
    analyzer_version: str = ANALYZER_VERSION
    taxonomy_version: str
    title: str
    seniority: str | None
    seniority_source: Literal["title", "min_years", "unknown"]
    role_families: list[str]
    min_years: float | None
    min_years_source: Literal["explicit", "text", "none"]
    requirements: list[SkillRequirement]
    focus_skills: list[str]
    unknown_explicit_skills: list[str] = []

    def by_importance(self, *levels: Importance) -> list[SkillRequirement]:
        return [r for r in self.requirements if r.importance in levels]

    @property
    def required(self) -> list[SkillRequirement]:
        return self.by_importance("critical", "required")

    @property
    def nice_to_have(self) -> list[SkillRequirement]:
        return self.by_importance("nice_to_have")


def _cue_of(text: str) -> Cue | None:
    for cue, pattern in _CUE_RES:
        if pattern.search(text):
            return cue
    return None


def _segment_cues(clause: str) -> list[tuple[str, Cue | None]]:
    """Split a clause that mixes cue types at commas ("X is required, Y is a plus")."""
    cues = {c for c, p in _CUE_RES if p.search(clause)}
    if len(cues) <= 1:
        return [(clause, _cue_of(clause))]
    segments = [(seg, _cue_of(seg)) for seg in clause.split(",")]
    resolved: list[tuple[str, Cue | None]] = []
    for i, (seg, cue) in enumerate(segments):
        if cue is None:
            following = [c for _, c in segments[i + 1 :] if c is not None]
            preceding = [c for _, c in segments[:i] if c is not None]
            cue = following[0] if following else (preceding[-1] if preceding else None)
        resolved.append((seg, cue))
    return resolved


def _is_heading(line: str, has_skills: bool) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("- ", "* ")):
        return False
    if stripped.endswith(":"):
        return True
    return not has_skills and len(stripped.split()) <= 6 and not stripped.endswith(".")


class _Accumulator:
    def __init__(self) -> None:
        self.best: dict[str, str] = {}
        self.mentions: Counter[str] = Counter()
        self.first_seen: dict[str, int] = {}
        self.skill_years: dict[str, float] = {}

    def add(self, skill: str, level: str, position: int) -> None:
        self.mentions[skill] += 1
        self.first_seen.setdefault(skill, position)
        current = self.best.get(skill)
        if current is None or _RANK[level] > _RANK[current]:
            self.best[skill] = level


def _years_in(text: str) -> float | None:
    values = [float(m.group("n")) for m in _YEARS_RE.finditer(text)]
    values = [v for v in values if 0 < v <= 30]
    return max(values) if values else None


def analyze_job(
    *,
    title: str,
    description: str,
    taxonomy: SkillTaxonomy,
    required_skills: list[str] | None = None,
    nice_to_have_skills: list[str] | None = None,
    critical_skills: list[str] | None = None,
    min_years: float | None = None,
) -> JobAnalysis:
    acc = _Accumulator()
    general_years: list[float] = []
    any_years: list[float] = []
    block: Cue | None = None
    position = 0

    for line in description.replace("\r\n", "\n").split("\n"):
        line_skills = taxonomy.find_names(line)
        if _is_heading(line, bool(line_skills)):
            block = _cue_of(line)  # "Responsibilities:" (no cue) resets the block
            if not line_skills:
                continue
        heading_label = line.split(":", 1)[0] if ":" in line else ""
        is_bullet = line.lstrip().startswith(("- ", "* "))
        # "Nice to have: Kafka" on its own line opens a block; inside a bullet the label
        # only applies to that bullet (handled by the clause cue below).
        if (
            not is_bullet
            and heading_label
            and _cue_of(heading_label)
            and len(heading_label.split()) <= 4
        ):
            block = _cue_of(heading_label)  # "Nice to have: Kafka" also opens a block
        for clause in filter(None, (c.strip() for c in _CLAUSE_SPLIT.split(line))):
            years = _years_in(clause)
            clause_skills = taxonomy.find_names(clause)
            if years is not None:
                any_years.append(years)
                if not clause_skills and re.search(
                    r"experience|engineering|development", clause, re.I
                ):
                    general_years.append(years)
                for skill in clause_skills:
                    acc.skill_years[skill] = max(acc.skill_years.get(skill, 0.0), years)
            for segment, cue in _segment_cues(clause):
                level = cue or block or "mention"
                for hit in taxonomy.find(segment):
                    acc.add(hit.skill, level, position)
                    position += 1

    requirements: dict[str, SkillRequirement] = {}
    for skill, level in acc.best.items():
        importance: Importance = (
            "critical" if level == "critical" else "nice_to_have" if level == "nice" else "required"
        )
        requirements[skill] = SkillRequirement(
            name=skill,
            category=taxonomy.category(skill),
            importance=importance,
            source="mentioned" if level == "mention" else "cue",
            min_years=acc.skill_years.get(skill),
            mentions=acc.mentions[skill],
        )

    unknown: list[str] = []
    explicit: list[tuple[list[str] | None, Importance]] = [
        (nice_to_have_skills, "nice_to_have"),
        (required_skills, "required"),
        (critical_skills, "critical"),
    ]
    for names, importance in explicit:
        for raw in names or []:
            canonical = taxonomy.canonical(raw)
            name = canonical or raw.strip()
            if not name:
                continue
            if canonical is None and name not in unknown:
                unknown.append(name)
            previous = requirements.get(name)
            requirements[name] = SkillRequirement(
                name=name,
                category=taxonomy.category(name) if canonical else "other",
                importance=importance,
                source="explicit",
                in_taxonomy=canonical is not None,
                min_years=previous.min_years if previous else None,
                mentions=previous.mentions if previous else 0,
            )

    order = {"critical": 0, "required": 1, "nice_to_have": 2}
    sorted_reqs = sorted(
        requirements.values(),
        key=lambda r: (order[r.importance], acc.first_seen.get(r.name, 10**6), r.name),
    )

    if min_years is not None:
        years, years_source = float(min_years), "explicit"
    elif general_years or any_years:
        years, years_source = max(general_years or any_years), "text"
    else:
        years, years_source = None, "none"

    seniority = detect_seniority(title)
    seniority_source: Literal["title", "min_years", "unknown"] = "title" if seniority else "unknown"
    if seniority is None and years is not None:
        seniority, seniority_source = seniority_from_years(years), "min_years"

    focus = [
        s for s, _ in sorted(acc.mentions.items(), key=lambda kv: (-kv[1], acc.first_seen[kv[0]]))
    ]

    return JobAnalysis(
        taxonomy_version=taxonomy.version,
        title=title.strip(),
        seniority=seniority,
        seniority_source=seniority_source,
        role_families=list(role_families(title)),
        min_years=years,
        min_years_source=years_source,
        requirements=sorted_reqs,
        focus_skills=focus[:5],
        unknown_explicit_skills=unknown,
    )


def literal_skill_pattern(name: str) -> re.Pattern[str]:
    """Boundary-safe matcher for explicit skills that are not in the taxonomy."""
    return re.compile(f"{LEFT_BOUNDARY}(?:{alias_pattern(name)}){RIGHT_BOUNDARY}", re.IGNORECASE)
