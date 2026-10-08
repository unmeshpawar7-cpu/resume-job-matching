from __future__ import annotations

from datetime import date

import pytest

from resume_matching.domain.experience import (
    merge_ranges,
    months_to_years,
    parse_date_ranges,
    stated_years,
    total_months,
)

TODAY = date(2026, 10, 8)


@pytest.mark.parametrize(
    ("text", "start", "end", "current"),
    [
        ("Jan 2021 – Present", "2021-01", "2026-10", True),
        ("January 2021 to Current", "2021-01", "2026-10", True),
        ("Sept. 2019 - Mar 2022", "2019-09", "2022-03", False),
        ("03/2019 – 05/2022", "2019-03", "2022-05", False),
        ("2019-03 – 2021-06", "2019-03", "2021-06", False),
        ("2019-2022", "2019-07", "2022-06", False),
        ("2019 – Present", "2019-07", "2026-10", True),
        ("2021 - 2021", "2021-07", "2021-12", False),
    ],
)
def test_parse_supported_formats(text, start, end, current):
    [rng] = parse_date_ranges(text, TODAY)
    assert rng.start.iso() == start
    assert rng.end.iso() == end
    assert rng.is_current is current


def test_invalid_and_future_ranges_are_skipped():
    assert parse_date_ranges("2023 - 2020", TODAY) == []
    assert parse_date_ranges("Jan 2030 - Present", TODAY) == []
    assert parse_date_ranges("Phone 555-2019", TODAY) == []
    [clipped] = parse_date_ranges("Jan 2025 - Dec 2029", TODAY)
    assert clipped.end.iso() == "2026-10"


def test_overlapping_ranges_are_not_double_counted():
    ranges = parse_date_ranges(
        "Jan 2018 - Dec 2020\nJun 2020 - Jun 2022\nJul 2022 - Dec 2022\nJan 2024 - Dec 2024",
        TODAY,
    )
    merged = merge_ranges(ranges)
    assert [(s.iso(), e.iso()) for s, e in merged] == [
        ("2018-01", "2022-12"),
        ("2024-01", "2024-12"),
    ]
    assert total_months(ranges) == 60 + 12
    assert months_to_years(total_months(ranges)) == 6.0


def test_three_year_range_counts_three_years():
    assert months_to_years(total_months(parse_date_ranges("2019 - 2022", TODAY))) == 3.0


def test_stated_years():
    assert stated_years("Engineer with 8+ years of experience in Python") == 8
    assert stated_years("5 years of backend experience; 3 yrs exp in Go") == 5
    assert stated_years("no claim here") is None
