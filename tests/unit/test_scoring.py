from __future__ import annotations

from datetime import date

import pytest

from resume_matching.ai.embeddings.hashing import HashingEmbeddingProvider
from resume_matching.core.config import ScoringSettings
from resume_matching.domain.job_analysis import analyze_job
from resume_matching.domain.profile import build_profile
from resume_matching.domain.scoring import ScoringInput, score_match, verdict_for
from resume_matching.domain.scoring.components import (
    calibration,
    cosine,
    coverage_score,
    experience_curve,
    semantic_component,
)
from resume_matching.domain.scoring.models import SkillMatch

TODAY = date(2026, 10, 8)
EMB = HashingEmbeddingProvider(256)

RESUME = """Alex Morgan
Senior Backend Engineer
alex@example.com | 12 Main Street, Springfield

Summary
Backend engineer building Python APIs.

Skills
Python, Flask, PostgreSQL, Docker, Redis

Experience
Senior Backend Engineer, Initech | Jan 2019 - Present
- Built REST APIs in Flask on PostgreSQL, deployed with Docker.
- Redis caching.
"""

JD = """Requirements:
- 5+ years of backend engineering experience
- Python, FastAPI, PostgreSQL, Docker
Nice to have:
- Kubernetes, Redis
"""


def compute(
    resume: str = RESUME,
    jd: str = JD,
    title: str = "Senior Backend Engineer",
    settings: ScoringSettings | None = None,
    taxonomy=None,
    with_vectors: bool = True,
    **job_kwargs,
):
    settings = settings or ScoringSettings(_env_file=None)
    profile, sections = build_profile(resume, taxonomy, TODAY)
    job = analyze_job(title=title, description=jd, taxonomy=taxonomy, **job_kwargs)
    scored = sections.scored()
    data = ScoringInput(
        profile=profile,
        job=job,
        resume_text="\n".join(scored.values()),
        section_vectors={k: EMB.embed_one(v) for k, v in scored.items()} if with_vectors else {},
        job_vector=EMB.embed_one(title + "\n" + jd) if with_vectors else None,
        embedding_provider="hashing",
    )
    return score_match(data, taxonomy, settings, "test-version")


def test_required_skill_credit_exact_related_missing(taxonomy):
    c = compute(taxonomy=taxonomy)
    by = {m.name: m for m in c.required_skills}
    assert by["Python"].match_type == "exact" and by["Python"].credit == 1.0
    assert by["Python"].evidenced is False  # only in summary/skills, not in a dated job
    assert by["PostgreSQL"].evidenced is True
    assert by["FastAPI"].match_type == "related"
    assert by["FastAPI"].via[0] == "Flask"
    assert by["FastAPI"].credit == 0.5
    # 3 exact + 0.5 related out of 4
    assert c.component("required_skills").score == pytest.approx(87.5)
    nice = {m.name: m.match_type for m in c.nice_to_have_skills}
    assert nice == {"Kubernetes": "related", "Redis": "exact"}  # Kubernetes via Docker
    assert c.component("nice_to_have").score == 75.0


def test_alias_match_reports_surface_form(taxonomy):
    c = compute(resume=RESUME.replace("Docker, Redis", "Docker, Redis, k8s"), taxonomy=taxonomy)
    k8s = next(m for m in c.nice_to_have_skills if m.name == "Kubernetes")
    assert k8s.match_type == "alias" and k8s.via == ["k8s"] and k8s.credit == 1.0


def test_critical_skills_weigh_more_and_knock_out(taxonomy):
    c = compute(taxonomy=taxonomy, critical_skills=["Terraform"])
    assert c.knockouts[0].code == "missing_critical_skill"
    assert c.knockouts[0].skills == ["Terraform"]
    assert c.raw_score > 40
    assert c.overall_score == 40.0
    # critical weight 2: (1 + 0.5 + 1 + 1 + 0 * 2) / (4 + 2)
    assert c.component("required_skills").score == pytest.approx(100 * 3.5 / 6, abs=0.05)
    assert c.recommendations[0].code == "missing_critical_skills"


def test_experience_curve_is_monotonic_and_capped():
    s = ScoringSettings(_env_file=None)
    points = [experience_curve(r / 10, s) for r in range(0, 31)]
    assert points == sorted(points)
    assert experience_curve(0.5, s) == 40.0
    assert experience_curve(1.0, s) == 90.0
    assert experience_curve(1.5, s) == 100.0
    assert experience_curve(3.0, s) == 100.0  # no over-qualification penalty
    assert experience_curve(0, s) == 0.0


def test_insufficient_experience_knock_out(taxonomy):
    jd = JD.replace("5+ years", "20+ years")
    c = compute(jd=jd, taxonomy=taxonomy)
    assert c.experience.ratio == pytest.approx(7.8 / 20, abs=0.01)
    assert any(k.code == "insufficient_experience" for k in c.knockouts)
    assert c.overall_score <= 60.0
    assert any(r.code == "experience_gap" for r in c.recommendations)


def test_components_not_applicable_redistribute_weight(taxonomy):
    c = compute(jd="We build APIs with Python.", taxonomy=taxonomy, with_vectors=False)
    assert c.component("nice_to_have").score is None
    assert c.component("experience").score is None
    assert c.component("semantic").score is None
    applicable = [x for x in c.components if x.score is not None]
    assert sum(x.effective_weight for x in applicable) == pytest.approx(1.0, abs=1e-3)
    assert c.overall_score == pytest.approx(sum(x.contribution for x in applicable), abs=0.1)


def test_weights_from_config_change_score_and_version(taxonomy):
    base = compute(taxonomy=taxonomy)
    skills_only = ScoringSettings(
        _env_file=None,
        weight_required_skills=1,
        weight_nice_to_have=0,
        weight_experience=0,
        weight_role=0,
        weight_semantic=0,
    )
    c = compute(taxonomy=taxonomy, settings=skills_only)
    assert c.overall_score == c.component("required_skills").score
    assert c.overall_score != base.overall_score
    default = ScoringSettings(_env_file=None)
    assert skills_only.scoring_version("m", "t") != default.scoring_version("m", "t")
    assert default.scoring_version("m", "t") != default.scoring_version("m2", "t")
    assert default.scoring_version("m", "t") == ScoringSettings(_env_file=None).scoring_version(
        "m", "t"
    )
    with pytest.raises(ValueError, match="weight"):
        ScoringSettings(
            _env_file=None,
            weight_required_skills=0,
            weight_nice_to_have=0,
            weight_experience=0,
            weight_role=0,
            weight_semantic=0,
        )


def test_scoring_is_deterministic(taxonomy):
    a = compute(taxonomy=taxonomy).model_dump()
    b = compute(taxonomy=taxonomy).model_dump()
    assert a == b


def test_score_ignores_name_contact_address_and_personal_sections(taxonomy):
    base = compute(taxonomy=taxonomy)
    variant = (
        RESUME.replace("Alex Morgan", "Fatima Al-Hassan").replace(
            "alex@example.com | 12 Main Street, Springfield",
            "fatima@example.org | Flat 3, 99 Long Road, Lagos | +44 20 7946 0958",
        )
        + "\nInterests\nMother of two, volunteer, chess, born 1975\n"
    )
    other = compute(resume=variant, taxonomy=taxonomy)
    assert other.overall_score == base.overall_score
    assert [x.score for x in other.components] == [x.score for x in base.components]


def test_role_component_uses_title_and_seniority(taxonomy):
    same = compute(taxonomy=taxonomy, title="Senior Backend Engineer")
    junior_job = compute(taxonomy=taxonomy, title="Junior Frontend Developer")
    assert same.role.title_similarity == 1.0
    assert same.role.seniority_fit == 1.0
    assert same.component("role").score == 100.0
    assert junior_job.component("role").score < same.component("role").score


def test_literal_requirement_not_in_taxonomy(taxonomy):
    resume = RESUME.replace("Redis caching.", "Redis caching and COBOL batch jobs.")
    c = compute(resume=resume, taxonomy=taxonomy, required_skills=["COBOL", "Fortran"])
    by = {m.name: m.match_type for m in c.required_skills}
    assert by["COBOL"] == "literal"
    assert by["Fortran"] == "missing"


def test_semantic_component_calibration_and_edge_cases():
    s = ScoringSettings(_env_file=None)
    score, detail = semantic_component([1.0, 0.0], {"skills": [1.0, 0.0]}, "hashing", s)
    assert score == 100.0 and detail.best_section == "skills"
    score, _ = semantic_component([1.0, 0.0], {"skills": [0.0, 1.0]}, "hashing", s)
    assert score == 0.0
    assert semantic_component(None, {}, "hashing", s)[0] is None
    assert calibration("openai", s) == (0.2, 0.7)
    assert cosine([0, 0], [1, 1]) == 0.0
    with pytest.raises(ValueError, match="dimension"):
        cosine([1, 0], [1, 0, 0])


def test_coverage_and_verdict_helpers():
    assert coverage_score([]) is None
    m = SkillMatch(name="X", category="c", importance="critical", match_type="missing", credit=0)
    n = SkillMatch(name="Y", category="c", importance="required", match_type="exact", credit=1)
    assert coverage_score([m, n], critical_weight=3) == 25.0
    assert [verdict_for(v) for v in (85, 70, 50, 10)] == ["strong", "good", "partial", "weak"]


def test_unevidenced_skills_produce_advice_and_topics(taxonomy):
    c = compute(taxonomy=taxonomy)
    codes = {r.code for r in c.recommendations}
    assert {"transferable_skill", "add_evidence"} <= codes
    topics = [t.topic for t in c.interview_topics]
    assert "Transfer from Flask to FastAPI" in topics
    assert any(t.endswith("in production") for t in topics)
    assert len(c.recommendations) <= 6 and len(c.interview_topics) <= 6
