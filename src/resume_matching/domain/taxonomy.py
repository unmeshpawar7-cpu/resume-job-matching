"""Curated skills taxonomy and word-boundary-safe alias matching.

Design notes
------------
* Each skill compiles to one regex: an alternation of its aliases, longest first, wrapped
  in *token boundaries* rather than ``\\b``. ``\\b`` is wrong for skills that start or end
  with punctuation (``C#``, ``C++``, ``.NET``, ``Node.js``): ``\\bC#\\b`` never matches
  because ``#`` is not a word character. Our boundaries are:

  - left:  not preceded by a word character or ``.`` (so ``js`` does not fire inside
    ``Node.js`` and ``.NET`` does not fire inside ``ASP.NET``);
  - right: not followed by a word character, ``+`` or ``#`` (so ``Java`` does not fire
    inside ``JavaScript`` and a bare ``C`` would never fire inside ``C#``/``C++``).

* Matching is per skill and may overlap across skills on purpose: ``SQL Server`` yields
  both *SQL Server* and *SQL*.
* Spaces inside an alias match any run of whitespace or hyphens (``event driven`` matches
  ``event-driven``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

LEFT_BOUNDARY = r"(?<![\w.])"
RIGHT_BOUNDARY = r"(?![\w+#])"


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...] = ()
    exact_case_aliases: tuple[str, ...] = ()
    related: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class SkillHit:
    """One occurrence of a skill in a piece of text."""

    skill: str
    surface: str  # the text as written, e.g. "k8s"
    start: int
    end: int

    @property
    def is_canonical(self) -> bool:
        return self.surface.casefold() == self.skill.casefold()


def alias_pattern(alias: str) -> str:
    parts = [re.escape(p) for p in alias.strip().split()]
    return r"[\s\-]+".join(parts)


class SkillTaxonomy:
    """Immutable, pre-compiled taxonomy. Build once at startup and share."""

    def __init__(self, skills: Iterable[Skill], version: str = "unversioned") -> None:
        self.version = version
        by_name: dict[str, Skill] = {}
        for skill in skills:
            key = skill.name.casefold()
            if key in by_name:
                raise ValueError(f"Duplicate skill in taxonomy: {skill.name}")
            by_name[key] = skill
        self._skills = by_name
        self._related = self._build_symmetric_relations()
        self._patterns = {s.name: self._compile(s) for s in by_name.values()}

    # ------------------------------------------------------------------ construction
    def _build_symmetric_relations(self) -> dict[str, frozenset[str]]:
        graph: dict[str, set[str]] = {s.name: set() for s in self._skills.values()}
        for skill in self._skills.values():
            for rel in skill.related:
                target = self._skills.get(rel.casefold())
                if target is None:
                    raise ValueError(f"Skill '{skill.name}' references unknown related '{rel}'")
                if target.name == skill.name:
                    continue
                graph[skill.name].add(target.name)
                graph[target.name].add(skill.name)
        return {k: frozenset(v) for k, v in graph.items()}

    @staticmethod
    def _compile(skill: Skill) -> re.Pattern[str]:
        insensitive = {a.casefold() for a in skill.aliases}
        if skill.name not in skill.exact_case_aliases:
            insensitive.add(skill.name.casefold())
        sensitive = set(skill.exact_case_aliases)
        alternatives: list[tuple[int, str]] = [(len(a), alias_pattern(a)) for a in insensitive] + [
            (len(a), f"(?-i:{alias_pattern(a)})") for a in sensitive
        ]
        alternatives.sort(key=lambda item: (-item[0], item[1]))
        body = "|".join(p for _, p in alternatives)
        return re.compile(f"{LEFT_BOUNDARY}(?:{body}){RIGHT_BOUNDARY}", re.IGNORECASE)

    # ------------------------------------------------------------------ queries
    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.casefold() in self._skills

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name.casefold())

    def canonical(self, name: str) -> str | None:
        """Resolve a free-text skill name (canonical or alias) to its canonical name."""
        cleaned = name.strip()
        if not cleaned:
            return None
        direct = self._skills.get(cleaned.casefold())
        if direct is not None:
            return direct.name
        hits = self.find(cleaned)
        # Accept only if one alias covers the whole input, e.g. "k8s" -> Kubernetes.
        full = [h for h in hits if h.start == 0 and h.end == len(cleaned)]
        return full[0].skill if full else None

    def category(self, name: str) -> str:
        skill = self.get(name)
        return skill.category if skill else "other"

    def related(self, name: str) -> frozenset[str]:
        skill = self.get(name)
        return self._related.get(skill.name, frozenset()) if skill else frozenset()

    def find(self, text: str) -> list[SkillHit]:
        """All skill occurrences in ``text`` ordered by position then skill name."""
        hits: list[SkillHit] = []
        for name, pattern in self._patterns.items():
            hits.extend(
                SkillHit(skill=name, surface=m.group(0), start=m.start(), end=m.end())
                for m in pattern.finditer(text)
            )
        hits.sort(key=lambda h: (h.start, h.skill))
        return hits

    def find_names(self, text: str) -> set[str]:
        return {h.skill for h in self.find(text)}


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)  # type: ignore[union-attr]


def load_taxonomy(path: Path | str) -> SkillTaxonomy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    skills: list[Skill] = []
    for entry in raw.get("skills", []):
        exact = list(_as_tuple(entry.get("exact_case_aliases")))
        name = str(entry["name"])
        if entry.get("name_case_sensitive"):
            exact.append(name)
        skills.append(
            Skill(
                name=name,
                category=str(entry.get("category", "other")),
                aliases=_as_tuple(entry.get("aliases")),
                exact_case_aliases=tuple(exact),
                related=frozenset(_as_tuple(entry.get("related"))),
            )
        )
    return SkillTaxonomy(skills, version=str(raw.get("version", "unversioned")))


@lru_cache(maxsize=4)
def cached_taxonomy(path: str) -> SkillTaxonomy:
    return load_taxonomy(path)
