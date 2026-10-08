"""Resume section detection.

A line is treated as a heading when, after stripping decoration (``#``, ``=``, ``-``, ``:``),
it equals a known heading phrase, e.g. ``WORK EXPERIENCE`` or ``Technical Skills:``. An inline
form ``Skills: Python, Docker`` starts the section and keeps the remainder as content.

Text before the first heading is the *header* (name, contact details). The header and
*personal* sections (interests, hobbies, spoken languages, references) are deliberately
excluded from skill extraction, embeddings and scoring - see the fairness notes in the README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

SectionType = Literal[
    "header",
    "summary",
    "experience",
    "skills",
    "education",
    "certifications",
    "projects",
    "other",
    "personal",
]

#: Sections that may influence a score.
SCORED_SECTIONS: tuple[SectionType, ...] = (
    "summary",
    "experience",
    "skills",
    "projects",
    "certifications",
    "education",
    "other",
)

_HEADINGS: dict[SectionType, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "career summary",
        "executive summary",
        "profile",
        "professional profile",
        "about",
        "about me",
        "objective",
        "career objective",
        "overview",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "professional background",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "skills and tools",
        "tools and technologies",
        "core competencies",
        "competencies",
        "technologies",
        "tech stack",
        "technical expertise",
        "technical proficiencies",
        "programming languages",
        "expertise",
    ),
    "education": (
        "education",
        "academic background",
        "education and training",
        "academics",
        "academic qualifications",
    ),
    "certifications": (
        "certifications",
        "certification",
        "certificates",
        "licenses and certifications",
        "licences and certifications",
        "certifications and training",
        "courses",
        "training",
    ),
    "projects": (
        "projects",
        "key projects",
        "selected projects",
        "personal projects",
        "side projects",
        "open source",
        "open source contributions",
    ),
    "other": (
        "awards",
        "achievements",
        "publications",
        "honors",
        "honours",
        "additional information",
    ),
    "personal": (
        "interests",
        "hobbies",
        "hobbies and interests",
        "languages",
        "spoken languages",
        "references",
        "personal details",
        "personal information",
        "volunteering",
        "volunteer experience",
    ),
}

_HEADING_LOOKUP: dict[str, SectionType] = {
    phrase: section for section, phrases in _HEADINGS.items() for phrase in phrases
}
_DECORATION = re.compile(r"^[^A-Za-z]+|[^A-Za-z)]+$")
_MAX_HEADING_LEN = 50
#: Sections whose body commonly contains "Label: value" lines ("Tech stack: ...",
#: "Languages: Python, C#") that must NOT be mistaken for a new section.
_LABELLED_CONTENT_SECTIONS: frozenset[SectionType] = frozenset({"experience", "projects", "skills"})


@dataclass(slots=True)
class ParsedSections:
    sections: dict[SectionType, str] = field(default_factory=dict)
    order: list[SectionType] = field(default_factory=list)
    headings_found: int = 0

    def get(self, section: SectionType) -> str:
        return self.sections.get(section, "")

    def scored(self) -> dict[SectionType, str]:
        return {s: t for s, t in self.sections.items() if s in SCORED_SECTIONS and t.strip()}


def _normalize_heading(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_heading(line: str) -> tuple[SectionType, str] | None:
    """Return ``(section, inline_remainder)`` if ``line`` is a section heading."""
    stripped = line.strip()
    if not stripped or stripped.startswith("- "):
        return None
    if ":" in stripped:
        head, rest = stripped.split(":", 1)
        section = _HEADING_LOOKUP.get(_normalize_heading(_DECORATION.sub("", head)))
        if section is not None and len(head) <= _MAX_HEADING_LEN:
            return section, rest.strip()
    if len(stripped) > _MAX_HEADING_LEN:
        return None
    section = _HEADING_LOOKUP.get(_normalize_heading(_DECORATION.sub("", stripped)))
    return (section, "") if section is not None else None


def detect_sections(text: str) -> ParsedSections:
    buckets: dict[SectionType, list[str]] = {}
    order: list[SectionType] = []
    current: SectionType = "header"
    headings = 0
    for line in text.split("\n"):
        heading = match_heading(line)
        if heading is not None and current in _LABELLED_CONTENT_SECTIONS:
            section, remainder = heading
            inline_label = bool(remainder)
            # "Languages" directly under Skills is a sub-heading for programming languages.
            sub_heading = (
                current == "skills" and section == "personal" and "languag" in line.lower()
            )
            if inline_label or sub_heading:
                heading = None
        if heading is not None:
            current, remainder = heading
            headings += 1
            if current not in order:
                order.append(current)
            if remainder:
                buckets.setdefault(current, []).append(remainder)
            continue
        if current == "header" and "header" not in order:
            order.append("header")
        buckets.setdefault(current, []).append(line)

    if headings == 0:
        # Unstructured resume: first paragraph is the header, the rest is "other".
        lines = text.split("\n")
        split_at = next((i for i, ln in enumerate(lines[:6]) if not ln.strip()), min(3, len(lines)))
        buckets = {"header": lines[:split_at], "other": lines[split_at:]}
        order = ["header", "other"]

    sections = {k: "\n".join(v).strip() for k, v in buckets.items()}
    return ParsedSections(
        sections={k: v for k, v in sections.items() if v},
        order=[s for s in order if sections.get(s)],
        headings_found=headings,
    )
