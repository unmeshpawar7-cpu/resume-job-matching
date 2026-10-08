"""Versioned prompt templates stored as Markdown files: ``prompts/<name>/<version>.md``.

A template has a ``## system`` and a ``## user`` section; ``{{placeholder}}`` markers in
the user section are substituted (no ``str.format`` so JSON braces need no escaping). The
version id (``match_explanation/v1``) is stored with every AI result.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
_SECTION_RE = re.compile(r"^## (system|user)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    user: str
    sha256: str

    @property
    def version_id(self) -> str:
        return f"{self.name}/{self.version}"

    def render_user(self, **values: str) -> str:
        text = self.user
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        if "{{" in text:
            missing = re.findall(r"\{\{(\w+)\}\}", text)
            raise ValueError(f"Unfilled prompt placeholders: {missing}")
        return text


@lru_cache
def load_prompt(name: str, version: str) -> PromptTemplate:
    path = PROMPTS_DIR / name / f"{version}.md"
    raw = path.read_text(encoding="utf-8")
    parts = _SECTION_RE.split(raw)
    sections = dict(zip(parts[1::2], (p.strip() for p in parts[2::2]), strict=True))
    if set(sections) != {"system", "user"}:
        raise ValueError(f"Prompt {path} must have exactly '## system' and '## user' sections")
    return PromptTemplate(
        name=name,
        version=version,
        system=sections["system"],
        user=sections["user"],
        sha256=hashlib.sha256(raw.encode()).hexdigest()[:12],
    )
