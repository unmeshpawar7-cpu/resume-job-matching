"""Job-title detection, normalisation, role families and seniority heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass

SENIORITY_LEVELS: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "principal": 5,
}
_SENIORITY_KEYWORDS: list[tuple[str, str]] = [
    # (regex, level) - checked in order, first match wins
    (r"\b(?:principal|distinguished|chief|head\s+of)\b", "principal"),
    (r"\barchitect\b", "principal"),
    (r"\b(?:lead|staff|team\s+lead|tech\s+lead)\b", "lead"),
    (r"\b(?:senior|sr\.?)(?=\W|$)|\biii\b", "senior"),
    (r"\b(?:mid|mid-level|intermediate)\b|\bii\b", "mid"),
    (r"\b(?:junior|jr\.?|graduate|entry[- ]level|associate)(?=\W|$)", "junior"),
    (r"\b(?:intern|internship|trainee|apprentice)\b", "intern"),
]
_ROLE_NOUNS = (
    "engineer",
    "developer",
    "programmer",
    "architect",
    "scientist",
    "analyst",
    "consultant",
    "administrator",
    "designer",
    "manager",
    "intern",
    "specialist",
)
_ROLE_NOUN_RE = re.compile(r"(?<![\w-])(?:" + "|".join(_ROLE_NOUNS) + r")s?(?![\w])", re.IGNORECASE)
_TITLE_MODIFIERS = {
    "software", "backend", "back-end", "frontend", "front-end", "full-stack", "fullstack",
    "full", "stack", "web", "data", "machine", "learning", "ml", "ai", "cloud", "platform",
    "devops", "site", "reliability", "mobile", "application", "applications", "systems",
    "solutions", "integration", "api", "python", "java", ".net", "c#", "node.js", "react",
    "analytics", "big", "research", "applied", "nlp", "llm", "infrastructure", "security",
    "qa", "test", "automation", "bi", "database", "senior", "sr", "sr.", "junior", "jr",
    "jr.", "lead", "principal", "staff", "associate", "graduate", "intern", "trainee",
    "engineering", "development", "product", "of", "and", "&", "/", "-", "mlops", "etl",
}  # fmt: skip
_CONNECTORS = {"of", "and", "&", "/", "-"}

_FAMILY_PATTERNS: dict[str, str] = {
    "fullstack": r"full[\s-]?stack",
    "frontend": r"front[\s-]?end|\bui\b|\breact\b|\bangular\b|\bvue\b",
    "backend": r"back[\s-]?end|server[\s-]?side|\bapi\b",
    "ml_ai": r"machine\s+learning|\bml\b|\bai\b|data\s+scien|deep\s+learning|\bnlp\b|\bllm|mlops"
    r"|applied\s+scien|research\s+scien",
    "data": r"data\s+engineer|analytics\s+engineer|\betl\b|big\s+data|data\s+platform"
    r"|\bbi\b|data\s+analyst",
    "devops": r"devops|\bsre\b|site\s+reliability|platform\s+engineer|cloud\s+engineer"
    r"|infrastructure",
    "mobile": r"mobile|android|\bios\b|flutter|react\s+native",
    "web": r"\bweb\b",
    "qa": r"\bqa\b|\bsdet\b|quality\s+assurance|\btest(?:ing)?\b",
    "management": r"engineering\s+manager|\bmanager\b|head\s+of|director|\bcto\b",
}
_FALLBACK_BACKEND = r"\.net|\bc#|\bjava\b|golang|\bnode|\bphp\b|\bruby\b|\bpython\b|\bdjango\b"
_GENERAL_SOFTWARE = r"software|programmer|developer|engineer"

#: Symmetric affinity between role families (1.0 for identical families).
_FAMILY_AFFINITY: dict[frozenset[str], float] = {
    frozenset({"fullstack", "backend"}): 0.75,
    frozenset({"fullstack", "frontend"}): 0.75,
    frozenset({"fullstack", "web"}): 0.75,
    frozenset({"frontend", "web"}): 0.9,
    frozenset({"backend", "web"}): 0.5,
    frozenset({"general_software", "backend"}): 0.75,
    frozenset({"general_software", "frontend"}): 0.75,
    frozenset({"general_software", "fullstack"}): 0.75,
    frozenset({"general_software", "mobile"}): 0.6,
    frozenset({"general_software", "ml_ai"}): 0.5,
    frozenset({"general_software", "data"}): 0.5,
    frozenset({"general_software", "devops"}): 0.5,
    frozenset({"general_software", "web"}): 0.6,
    frozenset({"ml_ai", "data"}): 0.5,
    frozenset({"backend", "data"}): 0.4,
    frozenset({"backend", "devops"}): 0.4,
    frozenset({"backend", "ml_ai"}): 0.3,
}

_TOKEN_SYNONYMS = {
    "developer": "engineer",
    "programmer": "engineer",
    "dev": "engineer",
    "eng": "engineer",
    "back-end": "backend",
    "front-end": "frontend",
    "full-stack": "fullstack",
    "machine": "ml",
    "learning": "",
    "artificial": "ai",
    "intelligence": "",
    "swe": "engineer",
}
_DROP_TOKENS = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate", "graduate",
    "mid", "level", "i", "ii", "iii", "iv", "of", "and", "the", "a", "an", "at", "for",
    "with", "to", "in", "head", "chief", "entry", "intern", "trainee", "-", "&", "/",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class TitleMatch:
    title: str
    seniority: str | None
    families: tuple[str, ...]


def detect_seniority(text: str) -> str | None:
    lowered = text.lower()
    for pattern, level in _SENIORITY_KEYWORDS:
        if re.search(pattern, lowered):
            return level
    return None


def seniority_from_years(years: float | None) -> str | None:
    """Fallback when no title keyword exists. Deliberately capped at *senior*: leadership
    level is never inferred from tenure alone."""
    if years is None:
        return None
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    return "senior"


def role_families(title: str) -> tuple[str, ...]:
    lowered = title.lower()
    families = [f for f, p in _FAMILY_PATTERNS.items() if re.search(p, lowered)]
    if not families and re.search(_FALLBACK_BACKEND, lowered):
        families.append("backend")
    if not families and re.search(_GENERAL_SOFTWARE, lowered):
        families.append("general_software")
    return tuple(families)


def family_affinity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return _FAMILY_AFFINITY.get(frozenset({a, b}), 0.0)


def family_score(candidate: tuple[str, ...], job: tuple[str, ...]) -> float | None:
    """Mean over the job's families of the best affinity with any candidate family."""
    if not job:
        return None
    if not candidate:
        return 0.0
    return sum(max(family_affinity(c, j) for c in candidate) for j in job) / len(job)


def normalize_title_tokens(title: str) -> set[str]:
    cleaned = re.sub(r"\([^)]*\)", " ", title.lower())  # drop "(Python/FastAPI)"
    cleaned = re.sub(r"full[\s-]stack", "fullstack", cleaned)
    cleaned = re.sub(r"back[\s-]end", "backend", cleaned)
    cleaned = re.sub(r"front[\s-]end", "frontend", cleaned)
    tokens: set[str] = set()
    for raw in re.split(r"[\s,|/]+", cleaned):
        token = raw.strip(".,:;()[]")
        if not token or token in _DROP_TOKENS:
            continue
        token = _TOKEN_SYNONYMS.get(token, token)
        if token and token not in _DROP_TOKENS:
            tokens.add(token)
    return tokens


def title_token_score(candidate: str, job: str) -> float:
    """Share of the job title's core tokens present in the candidate title (0..1)."""
    job_tokens = normalize_title_tokens(job)
    if not job_tokens:
        return 0.0
    return len(job_tokens & normalize_title_tokens(candidate)) / len(job_tokens)


def title_similarity(candidate: str, job: str) -> float:
    tokens = title_token_score(candidate, job)
    fam = family_score(role_families(candidate), role_families(job))
    if fam is None:
        return tokens
    return round(0.6 * tokens + 0.4 * fam, 4)


def extract_title(line: str) -> str | None:
    """Extract a job title from a short header-like line.

    Finds the first role noun and walks backwards over capitalised words or known title
    modifiers ("Senior Python Backend Developer — Contoso" -> "Senior Python Backend
    Developer"; "Worked as a Python developer" -> "Python developer").
    """
    text = line.strip()
    if not text or len(text) > 120 or text.startswith("- "):
        return None
    match = _ROLE_NOUN_RE.search(text)
    if match is None:
        return None
    prefix_words = text[: match.start()].split()
    collected: list[str] = []
    for word in reversed(prefix_words):
        # Separators ("Contoso," "Present:" "|" "—") end the title.
        if not re.search(r"[A-Za-z]", word) or word.endswith((",", ";", ":", "|", ")")):
            break
        if word.lower() in _TITLE_MODIFIERS or word[0].isupper() or word.startswith("."):
            collected.append(word)
        else:
            break
        if len(collected) >= 5:
            break
    while collected and collected[-1].lower() in _CONNECTORS:
        collected.pop()
    words = [*reversed(collected), match.group(0)]
    tail = text[match.end() :]
    level = re.match(r"\s+(I{1,3}|IV|[1-4])\b", tail)
    if level:
        words.append(level.group(1))
    title = " ".join(words).strip()
    return title or None


def analyze_title(title: str) -> TitleMatch:
    return TitleMatch(title=title, seniority=detect_seniority(title), families=role_families(title))


def seniority_fit(candidate: str | None, job: str | None) -> float | None:
    """1.0 on target; mild discount when above (no over-qualification penalty beyond that,
    which could act as an age proxy); steeper when below. ``None`` if either side unknown."""
    if candidate is None or job is None:
        return None
    diff = SENIORITY_LEVELS[candidate] - SENIORITY_LEVELS[job]
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.9
    if diff >= 2:
        return 0.8
    if diff == -1:
        return 0.6
    if diff == -2:
        return 0.3
    return 0.0
