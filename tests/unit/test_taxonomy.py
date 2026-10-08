from __future__ import annotations

import pytest

from resume_matching.domain.taxonomy import Skill, SkillTaxonomy, load_taxonomy


@pytest.mark.parametrize(
    ("text", "present", "absent"),
    [
        ("Senior JavaScript developer", {"JavaScript"}, {"Java"}),
        ("Java 17 and Spring Boot", {"Java", "Spring Boot"}, {"JavaScript"}),
        ("C# with .NET 8 and ASP.NET Core", {"C#", ".NET", "ASP.NET Core"}, {"C++"}),
        ("Modern C++ (C++20)", {"C++"}, {"C#"}),
        ("APIs on Node.js and Express.js", {"Node.js", "Express.js"}, {"JavaScript"}),
        ("Deployed to k8s with Helm", {"Kubernetes", "Helm"}, set()),
        ("Go and golang services", {"Go"}, set()),
        ("We go to production weekly", set(), {"Go"}),
        ("SQL Server and T-SQL tuning", {"SQL Server", "T-SQL", "SQL"}, set()),
        ("event-driven systems", {"Event-Driven Architecture"}, set()),
    ],
)
def test_alias_matching_is_boundary_safe(taxonomy, text, present, absent):
    found = taxonomy.find_names(text)
    assert present <= found
    assert not (absent & found)


def test_hits_report_surface_form_and_position(taxonomy):
    hits = [h for h in taxonomy.find("Ops: k8s") if h.skill == "Kubernetes"]
    assert hits[0].surface == "k8s"
    assert hits[0].start == 5
    assert not hits[0].is_canonical


def test_canonical_resolution(taxonomy):
    assert taxonomy.canonical("k8s") == "Kubernetes"
    assert taxonomy.canonical("  fastapi ") == "FastAPI"
    assert taxonomy.canonical("dotnet") == ".NET"
    assert taxonomy.canonical("Kubernetes operators") is None
    assert taxonomy.canonical("") is None
    assert taxonomy.canonical("COBOL") is None


def test_related_skills_are_symmetric(taxonomy):
    assert "Flask" in taxonomy.related("FastAPI")
    assert "FastAPI" in taxonomy.related("Flask")
    assert taxonomy.related("Unknown") == frozenset()
    assert taxonomy.category("PostgreSQL") == "database"
    assert taxonomy.category("Unknown") == "other"
    assert "Python" in taxonomy and "COBOL" not in taxonomy


def test_taxonomy_validation(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        SkillTaxonomy([Skill("A", "x"), Skill("a", "x")])
    with pytest.raises(ValueError, match="unknown related"):
        SkillTaxonomy([Skill("A", "x", related=frozenset({"B"}))])
    path = tmp_path / "t.yaml"
    path.write_text(
        "version: '9'\nskills:\n  - {name: Go, category: language, name_case_sensitive: true}\n"
        "  - {name: Ruby, category: language, aliases: rb}\n",
        encoding="utf-8",
    )
    tax = load_taxonomy(path)
    assert tax.version == "9"
    assert len(tax) == 2
    assert tax.find_names("go home") == set()
    assert tax.find_names("rb and Go") == {"Ruby", "Go"}


def test_generic_words_do_not_trigger_case_sensitive_skills(taxonomy):
    assert "SOLID" not in taxonomy.find_names("Solid backend profile with solid testing")
    assert "SOLID" in taxonomy.find_names("Clean, SOLID code and solid principles")
