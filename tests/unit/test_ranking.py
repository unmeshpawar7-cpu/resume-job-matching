from __future__ import annotations

from datetime import datetime

from resume_matching.domain.ranking import RankEntry, rank, top_reasons
from tests.unit.test_scoring import compute


def _entry(computation, rid, minute):
    return RankEntry(
        resume_id=rid, created_at=datetime(2026, 1, 1, 0, minute), computation=computation
    )


def test_rank_orders_by_score_then_tie_breakers(taxonomy):
    strong = compute(taxonomy=taxonomy)
    weak = compute(taxonomy=taxonomy, critical_skills=["Terraform"])
    tie_a = _entry(strong, "b-resume", 5)
    tie_b = _entry(strong, "a-resume", 9)
    tie_c = _entry(strong, "c-resume", 5)
    ordered = rank([_entry(weak, "w", 1), tie_b, tie_c, tie_a])
    # equal scores -> earlier upload first, then resume id
    assert [e.resume_id for e in ordered] == ["b-resume", "c-resume", "a-resume", "w"]
    assert [e.resume_id for e in rank([tie_a, _entry(weak, "w", 1)], min_score=50)] == ["b-resume"]


def test_rank_prefers_required_coverage_on_equal_score(taxonomy):
    a = compute(taxonomy=taxonomy)
    b = a.model_copy(deep=True)
    b.component("required_skills").score = 10.0
    ordered = rank([_entry(b, "low-coverage", 0), _entry(a, "high-coverage", 30)])
    assert ordered[0].resume_id == "high-coverage"


def test_top_reasons(taxonomy):
    reasons = top_reasons(compute(taxonomy=taxonomy, critical_skills=["Terraform"]), limit=5)
    assert reasons[0].startswith("Missing must-have skill(s): Terraform")
    assert any(r.startswith("Matches 3/5 required skills") for r in reasons)
    assert any("years experience vs 5+ required" in r for r in reasons)
    assert len(top_reasons(compute(taxonomy=taxonomy))) == 3
