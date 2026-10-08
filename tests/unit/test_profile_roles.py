from __future__ import annotations

from datetime import date

import pytest

from resume_matching.domain.profile import build_profile
from resume_matching.domain.roles import (
    detect_seniority,
    extract_title,
    family_score,
    role_families,
    seniority_fit,
    seniority_from_years,
    title_similarity,
)
from tests.conftest import SAMPLES

TODAY = date(2026, 10, 8)


def test_sample_profile_positions_and_recency(taxonomy):
    text = (SAMPLES / "resumes" / "daniel_okafor_ai_backend.txt").read_text()
    profile, _ = build_profile(text, taxonomy, TODAY)
    assert len(profile.experience.positions) == 3
    assert profile.experience.positions[0].is_current
    assert profile.titles[0] == "Senior Backend Engineer"
    fastapi = profile.skill_map()["FastAPI"]
    assert fastapi.evidenced and fastapi.last_used == "present"
    assert fastapi.years_used == pytest.approx(4.7, abs=0.1)
    assert all("@" not in s for e in profile.skills for s in e.snippets)


def test_profile_warnings_for_unstructured_text(taxonomy):
    profile, _ = build_profile(
        "Sam\n\nDeveloper with 6 years of experience in Python and Django.", taxonomy, TODAY
    )
    assert profile.experience.source == "stated"
    assert profile.experience.total_years == 6
    assert profile.seniority == "senior" and profile.seniority_source == "years"
    assert any("No section headings" in w for w in profile.warnings)
    empty, _ = build_profile("Sam\n\nLikes Python.", taxonomy, TODAY)
    assert empty.experience.source == "none"


@pytest.mark.parametrize(
    ("line", "title"),
    [
        ("Senior Python Backend Developer - Contoso", "Senior Python Backend Developer"),
        ("Worked as a Python developer", "Python developer"),
        ("Software Engineer II at Initech", "Software Engineer II"),
        ("Nothing here", None),
    ],
)
def test_extract_title(line, title):
    assert extract_title(line) == title


def test_seniority_helpers():
    assert detect_seniority("Sr. Engineer") == "senior"
    assert detect_seniority("Staff Engineer") == "lead"
    assert detect_seniority("Graduate Developer") == "junior"
    assert detect_seniority("Engineer") is None
    assert [seniority_from_years(y) for y in (None, 1, 3, 12)] == [None, "junior", "mid", "senior"]
    assert seniority_fit("senior", "senior") == 1.0
    assert seniority_fit("principal", "mid") == 0.8
    assert seniority_fit("junior", "senior") == 0.3
    assert seniority_fit("intern", "lead") == 0.0
    assert seniority_fit(None, "mid") is None


def test_title_similarity_and_families():
    assert title_similarity("Backend Developer", "Back-end Engineer") == 1.0
    assert title_similarity("Data Engineer", "Frontend Engineer") < 0.5
    assert role_families("Senior .NET Developer") == ("backend",)
    assert role_families("Software Engineer") == ("general_software",)
    assert family_score((), ("backend",)) == 0.0
    assert family_score(("backend",), ()) is None
