"""Builds the structured, scoring-ready :class:`ResumeProfile` from extracted resume text.

Only *scored* sections feed the profile. The header (name, contact details, location) and
personal sections are excluded by construction, so they cannot influence any score. The
one exception is that the header is scanned for a job title using the role-noun extractor,
which by design only returns phrases ending in a role noun ("Senior Backend Engineer").
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from resume_matching.domain.base import DomainModel
from resume_matching.domain.experience import (
    DateRange,
    months_to_years,
    parse_date_ranges,
    stated_years,
    total_months,
)
from resume_matching.domain.roles import (
    detect_seniority,
    extract_title,
    role_families,
    seniority_from_years,
)
from resume_matching.domain.sections import ParsedSections, detect_sections
from resume_matching.domain.taxonomy import SkillTaxonomy

PARSER_VERSION = "1.0.0"
EVIDENCE_SECTIONS = frozenset({"experience", "projects"})
_MAX_SNIPPETS = 2
_SNIPPET_LEN = 160


class SkillEvidence(DomainModel):
    name: str
    category: str
    mentions: int
    sections: list[str]
    surface_forms: list[str]
    evidenced: bool  # appears in experience or projects, not only in a skills list
    last_used: str | None = None  # "YYYY-MM" or "present"
    years_used: float | None = None
    snippets: list[str] = []


class Position(DomainModel):
    title: str | None
    start: str
    end: str
    is_current: bool
    months: int
    skills: list[str]


class ExperienceSummary(DomainModel):
    total_years: float
    source: Literal["date_ranges", "stated", "none"]
    stated_years: float | None
    date_ranges_found: int
    positions: list[Position]


class SectionSummary(DomainModel):
    type: str
    characters: int


class ResumeProfile(DomainModel):
    parser_version: str = PARSER_VERSION
    taxonomy_version: str
    sections: list[SectionSummary]
    skills: list[SkillEvidence]
    experience: ExperienceSummary
    titles: list[str]
    current_title: str | None
    role_families: list[str]
    seniority: str | None
    seniority_source: Literal["title", "years", "unknown"]
    certifications: list[str]
    warnings: list[str] = []

    def skill_map(self) -> dict[str, SkillEvidence]:
        return {s.name: s for s in self.skills}


def _snippet(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line = text[line_start : line_end if line_end != -1 else len(text)].strip()
    line = line.removeprefix("- ")
    if len(line) <= _SNIPPET_LEN:
        return line
    offset = max(0, (start - line_start) - _SNIPPET_LEN // 2)
    return "..." + line[offset : offset + _SNIPPET_LEN].strip() + "..."


def _extract_skills(sections: ParsedSections, taxonomy: SkillTaxonomy) -> dict[str, SkillEvidence]:
    found: dict[str, SkillEvidence] = {}
    for section, text in sections.scored().items():
        for hit in taxonomy.find(text):
            ev = found.get(hit.skill)
            if ev is None:
                ev = SkillEvidence(
                    name=hit.skill,
                    category=taxonomy.category(hit.skill),
                    mentions=0,
                    sections=[],
                    surface_forms=[],
                    evidenced=False,
                )
                found[hit.skill] = ev
            ev.mentions += 1
            if section not in ev.sections:
                ev.sections.append(section)
            if hit.surface not in ev.surface_forms:
                ev.surface_forms.append(hit.surface)
            if section in EVIDENCE_SECTIONS:
                ev.evidenced = True
            snippet = _snippet(text, hit.start, hit.end)
            if (
                section != "skills"
                and len(ev.snippets) < _MAX_SNIPPETS
                and snippet not in ev.snippets
            ):
                ev.snippets.append(snippet)
    return found


def _is_bullet(line: str) -> bool:
    return line.lstrip().startswith(("- ", "* "))


def _extract_positions(
    text: str, taxonomy: SkillTaxonomy, today: date
) -> tuple[list[Position], list[DateRange]]:
    lines = text.split("\n")
    dated: list[tuple[int, DateRange]] = []
    for i, line in enumerate(lines):
        ranges = parse_date_ranges(line, today)
        if ranges:
            dated.append((i, ranges[0]))
    # Header of an entry = the date line, plus the line just above it when that line is a
    # non-bullet title/company line ("Senior Engineer - Contoso" / "Jan 2021 - Present").
    starts: list[int] = []
    for i, _ in dated:
        prev = i - 1
        has_title_line = (
            prev >= 0
            and lines[prev].strip()
            and not _is_bullet(lines[prev])
            and all(prev != d for d, _ in dated)
            and (not starts or prev > starts[-1])
        )
        starts.append(prev if has_title_line else i)

    positions: list[Position] = []
    all_ranges: list[DateRange] = []
    for k, (line_idx, rng) in enumerate(dated):
        block_start = starts[k]
        block_end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        block = "\n".join(lines[block_start:block_end])
        title = extract_title(lines[line_idx].replace(rng.raw, " | "))
        if title is None and block_start < line_idx:
            title = extract_title(lines[block_start])
        positions.append(
            Position(
                title=title,
                start=rng.start.iso(),
                end="present" if rng.is_current else rng.end.iso(),
                is_current=rng.is_current,
                months=rng.months,
                skills=sorted(taxonomy.find_names(block)),
            )
        )
        all_ranges.append(rng)
    return positions, all_ranges


def _apply_recency(
    skills: dict[str, SkillEvidence], positions: list[Position], ranges: list[DateRange]
) -> None:
    for name, ev in skills.items():
        used = [(p, r) for p, r in zip(positions, ranges, strict=True) if name in p.skills]
        if not used:
            continue
        ev.years_used = months_to_years(total_months([r for _, r in used]))
        if any(p.is_current for p, _ in used):
            ev.last_used = "present"
        else:
            ev.last_used = max(r.end for _, r in used).iso()


def _collect_titles(
    sections: ParsedSections, positions: list[Position]
) -> tuple[list[str], str | None]:
    ordered = sorted(
        (p for p in positions if p.title),
        key=lambda p: ("9999-99" if p.is_current else p.end, p.start),
        reverse=True,
    )
    position_titles = [p.title for p in ordered if p.title]
    header_titles = [
        t for t in (extract_title(ln) for ln in sections.get("header").split("\n")[:8]) if t
    ]
    summary = sections.get("summary").split("\n")[0][:120]
    summary_titles = [t for t in [extract_title(summary)] if t]

    titles: list[str] = []
    for t in position_titles + header_titles + summary_titles:
        if t.casefold() not in {x.casefold() for x in titles}:
            titles.append(t)
    current = (position_titles or header_titles or summary_titles or [None])[0]
    return titles, current


def build_profile(
    text: str, taxonomy: SkillTaxonomy, today: date
) -> tuple[ResumeProfile, ParsedSections]:
    sections = detect_sections(text)
    warnings: list[str] = []
    if sections.headings_found == 0:
        warnings.append(
            "No section headings detected; the document was treated as unstructured text."
        )

    skills = _extract_skills(sections, taxonomy)

    experience_text = sections.get("experience")
    if not experience_text:
        experience_text = sections.get("other")
        warnings.append(
            "No experience section detected; date ranges were read from unlabelled text."
        )
    positions, ranges = _extract_positions(experience_text, taxonomy, today)
    _apply_recency(skills, positions, ranges)

    stated = stated_years(
        " ".join([sections.get("summary"), sections.get("experience"), sections.get("other")])
    )
    if ranges:
        total_years, source = months_to_years(total_months(ranges)), "date_ranges"
    elif stated is not None:
        total_years, source = stated, "stated"
        warnings.append("No employment date ranges found; using the stated years of experience.")
    else:
        total_years, source = 0.0, "none"
        warnings.append("No employment dates or stated years of experience found.")

    titles, current_title = _collect_titles(sections, positions)
    seniority = detect_seniority(current_title) if current_title else None
    seniority_source: Literal["title", "years", "unknown"] = "title" if seniority else "unknown"
    if seniority is None and source != "none":
        seniority, seniority_source = seniority_from_years(total_years), "years"

    families: list[str] = []
    for t in titles[:2]:
        for fam in role_families(t):
            if fam not in families:
                families.append(fam)

    certifications = [
        ln.removeprefix("- ").strip()[:120]
        for ln in sections.get("certifications").split("\n")
        if ln.strip()
    ][:10]

    profile = ResumeProfile(
        taxonomy_version=taxonomy.version,
        sections=[SectionSummary(type=s, characters=len(t)) for s, t in sections.scored().items()],
        skills=sorted(skills.values(), key=lambda s: (-s.mentions, s.name)),
        experience=ExperienceSummary(
            total_years=total_years,
            source=source,
            stated_years=stated,
            date_ranges_found=len(ranges),
            positions=positions,
        ),
        titles=titles,
        current_title=current_title,
        role_families=families,
        seniority=seniority,
        seniority_source=seniority_source,
        certifications=certifications,
        warnings=warnings,
    )
    return profile, sections
