from __future__ import annotations

from resume_matching.domain.job_analysis import analyze_job

JD = """Backend Engineer

Requirements:
- 4+ years of backend development experience
- Python and PostgreSQL
- Docker is required, Kubernetes is a plus

Nice to have:
- Terraform
- GraphQL

Must have: FastAPI.
Responsibilities:
- Build APIs with Redis caching
"""


def _imp(analysis):
    return {r.name: r.importance for r in analysis.requirements}


def test_cue_classification(taxonomy):
    a = analyze_job(title="Senior Backend Engineer", description=JD, taxonomy=taxonomy)
    imp = _imp(a)
    assert imp["Python"] == "required"
    assert imp["PostgreSQL"] == "required"
    assert imp["Docker"] == "required"
    assert imp["Kubernetes"] == "nice_to_have"
    assert imp["Terraform"] == "nice_to_have"
    assert imp["GraphQL"] == "nice_to_have"
    assert imp["FastAPI"] == "critical"
    assert imp["Redis"] == "required"  # un-cued mention => required
    assert a.min_years == 4
    assert a.min_years_source == "text"
    assert a.seniority == "senior"
    assert a.seniority_source == "title"
    assert "backend" in a.role_families
    assert [r.importance for r in a.requirements][:1] == ["critical"]


def test_explicit_lists_override_text(taxonomy):
    a = analyze_job(
        title="Engineer",
        description=JD,
        taxonomy=taxonomy,
        required_skills=["k8s", "COBOL"],
        nice_to_have_skills=["Python"],
        critical_skills=["Docker"],
        min_years=2,
    )
    imp = _imp(a)
    assert imp["Kubernetes"] == "required"
    assert imp["Python"] == "nice_to_have"
    assert imp["Docker"] == "critical"
    assert imp["COBOL"] == "required"
    assert a.unknown_explicit_skills == ["COBOL"]
    cobol = next(r for r in a.requirements if r.name == "COBOL")
    assert cobol.in_taxonomy is False
    assert a.min_years == 2 and a.min_years_source == "explicit"
    assert a.seniority == "mid" and a.seniority_source == "min_years"


def test_bullet_inline_label_does_not_open_block(taxonomy):
    jd = "Requirements:\n- Must have: Python\n- SQL\n"
    imp = _imp(analyze_job(title="Dev", description=jd, taxonomy=taxonomy))
    assert imp == {"Python": "critical", "SQL": "required"}


def test_no_years_and_no_title_seniority(taxonomy):
    a = analyze_job(title="Developer", description="We use React daily.", taxonomy=taxonomy)
    assert a.min_years is None and a.min_years_source == "none"
    assert a.seniority is None and a.seniority_source == "unknown"
    assert a.focus_skills == ["React"]
