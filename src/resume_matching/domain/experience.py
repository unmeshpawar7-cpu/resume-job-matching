"""Employment date-range parsing and overlap-aware experience totals.

Supported range forms (case-insensitive, any of ``-`` ``–`` ``—`` ``to`` ``until`` ``through``):

* ``Jan 2021 – Present``, ``January 2021 to Current``, ``Sept. 2019 - Mar 2022``
* ``03/2019 – 05/2022``, ``3.2019 - 11.2020``, ``2019-03 – 2021-06`` (ISO year-month)
* ``2019-2022``, ``2019 – Present`` (year precision)

Year-only dates use a documented *mid-year* convention so that ``2019 - 2022`` counts as
3 years rather than 4 (inclusive Jan-Dec) or 2 (exclusive): a year-only start is read as
July, a year-only end as June (or December when start and end are in the same year).

Totals merge overlapping ranges first, so concurrent jobs are never double counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_RE = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_YEAR = r"(?:19|20)\d{2}"


def _date_pattern(p: str) -> str:
    return (
        rf"(?:(?P<{p}m>{_MONTH_RE})\.?\s*,?\s*'?(?P<{p}y>{_YEAR})"
        rf"|(?P<{p}nm>0?[1-9]|1[0-2])\s*[/.]\s*(?P<{p}ny>{_YEAR})"
        rf"|(?P<{p}iy>{_YEAR})[/.\-](?P<{p}im>0[1-9]|1[0-2])(?![\d])"
        rf"|(?P<{p}yo>{_YEAR}))"
    )


_PRESENT = r"(?P<present>present|current(?:ly)?|now|today|ongoing|till\s+date|to\s+date|date)"
_SEPARATOR = r"\s*(?:-|–|—|~|\bto\b|\buntil\b|\btill\b|\bthrough\b|\bthru\b)\s*"
_RANGE_RE = re.compile(
    rf"(?<![\d/.])(?:{_date_pattern('s')}){_SEPARATOR}(?:{_date_pattern('e')}|{_PRESENT})(?![\d])",
    re.IGNORECASE,
)
_STATED_YEARS_RE = re.compile(
    r"(?P<n>\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+[\w.#+/-]+){0,3}?"
    r"\s+(?:experience|exp)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, order=True)
class YearMonth:
    year: int
    month: int

    @property
    def index(self) -> int:
        return self.year * 12 + (self.month - 1)

    @classmethod
    def from_index(cls, index: int) -> YearMonth:
        return cls(index // 12, index % 12 + 1)

    @classmethod
    def from_date(cls, d: date) -> YearMonth:
        return cls(d.year, d.month)

    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class DateRange:
    start: YearMonth
    end: YearMonth
    is_current: bool
    raw: str

    @property
    def months(self) -> int:
        """Inclusive month count (Jan-Mar = 3)."""
        return self.end.index - self.start.index + 1


def _side(match: re.Match[str], p: str) -> tuple[int, int | None] | None:
    """Return ``(year, month or None)`` for side ``p`` of a range match."""
    if match.group(f"{p}y"):
        return int(match.group(f"{p}y")), _MONTHS[match.group(f"{p}m")[:3].lower()]
    if match.group(f"{p}ny"):
        return int(match.group(f"{p}ny")), int(match.group(f"{p}nm"))
    if match.group(f"{p}iy"):
        return int(match.group(f"{p}iy")), int(match.group(f"{p}im"))
    if match.group(f"{p}yo"):
        return int(match.group(f"{p}yo")), None
    return None


def parse_date_ranges(text: str, today: date) -> list[DateRange]:
    """Find all employment-style date ranges in ``text``. Invalid ranges are skipped."""
    now = YearMonth.from_date(today)
    ranges: list[DateRange] = []
    for match in _RANGE_RE.finditer(text):
        start_side = _side(match, "s")
        if start_side is None:  # pragma: no cover - regex guarantees a start
            continue
        start_year, start_month = start_side
        start = YearMonth(start_year, start_month or 7)
        is_current = bool(match.group("present"))
        if is_current:
            end = now
        else:
            end_side = _side(match, "e")
            if end_side is None:  # pragma: no cover
                continue
            end_year, end_month = end_side
            if end_month is None:
                end_month = 6 if end_year > start.year else 12
            end = YearMonth(end_year, end_month)
        if start > now:
            continue
        end = min(end, now)
        if end < start:
            continue
        ranges.append(DateRange(start=start, end=end, is_current=is_current, raw=match.group(0)))
    return ranges


def merge_ranges(ranges: list[DateRange]) -> list[tuple[YearMonth, YearMonth]]:
    """Merge overlapping or adjacent ranges into disjoint inclusive intervals."""
    intervals = sorted((r.start.index, r.end.index) for r in ranges)
    merged: list[list[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(YearMonth.from_index(s), YearMonth.from_index(e)) for s, e in merged]


def total_months(ranges: list[DateRange]) -> int:
    return sum(e.index - s.index + 1 for s, e in merge_ranges(ranges))


def months_to_years(months: int) -> float:
    return round(months / 12, 1)


def stated_years(text: str) -> float | None:
    """Largest explicit "N+ years of experience" claim, if any."""
    values = [float(m.group("n")) for m in _STATED_YEARS_RE.finditer(text)]
    values = [v for v in values if 0 < v <= 50]
    return max(values) if values else None
