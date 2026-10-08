from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from resume_matching.ai.contracts import ExplanationFacts, MatchExplanation, build_facts
from resume_matching.ai.explanation import ExplanationGenerator, grounding_violations
from resume_matching.ai.llm import OfflineTemplateProvider, build_llm_provider
from resume_matching.ai.llm.anthropic import AnthropicProvider
from resume_matching.ai.llm.base import LLMRequest, extract_json_object, is_transient
from resume_matching.ai.llm.openai import OpenAIProvider
from resume_matching.ai.narrative import render_explanation
from resume_matching.ai.prompts import load_prompt
from resume_matching.ai.usage import estimate_cost, estimate_tokens, usage_scope
from resume_matching.core.errors import ProviderError
from tests.conftest import ScriptedLLM, make_settings
from tests.unit.test_scoring import compute


@pytest.fixture
def facts(taxonomy) -> ExplanationFacts:
    return build_facts(compute(taxonomy=taxonomy, critical_skills=["Terraform"]), taxonomy)


def answer(**overrides) -> str:
    base = {
        "summary": "Solid backend profile with Python and PostgreSQL in production.",
        "strengths": ["Python", "PostgreSQL"],
        "gaps": ["Terraform is missing"],
        "skills_mentioned": ["Python", "PostgreSQL", "Terraform"],
    }
    base.update(overrides)
    return json.dumps(base)


def test_facts_contain_no_pii_and_list_allowed_skills(facts):
    dumped = json.dumps(facts.to_json_dict())
    assert "alex@example.com" not in dumped
    assert "Alex Morgan" not in dumped
    assert "Main Street" not in dumped
    assert facts.critical_missing == ["Terraform"]
    assert {"Python", "FastAPI", "Flask", "Terraform"} <= set(facts.allowed_skills)


def test_template_narrative_is_grounded(facts, taxonomy):
    explanation = render_explanation(facts)
    assert grounding_violations(explanation, facts, taxonomy) == []
    assert f"{facts.overall_score:g}/100" in explanation.summary
    assert any("Terraform" in g for g in explanation.gaps)


def test_grounding_detects_unknown_skills_and_changed_numbers(facts, taxonomy):
    bad = MatchExplanation(
        summary="Expert in Rust; overall a 97% match, mentoring juniors.",
        strengths=["Rust"],
        gaps=[],
        skills_mentioned=["Rust", "Haskell", "k8s", "Python"],
    )
    problems = grounding_violations(bad, facts, taxonomy)
    assert any("'Rust'" in p and "skills_mentioned" in p for p in problems)
    assert any("'Haskell'" in p for p in problems)
    assert not any("'k8s'" in p for p in problems)  # alias of an allowed skill
    assert any("text mentions 'Rust'" in p for p in problems)
    assert any("97%" in p for p in problems)
    assert not any("Mentoring" in p for p in problems)  # practice words are ignored in prose
    ok = MatchExplanation(
        summary=f"Overall {facts.overall_score}% with Python.", skills_mentioned=["python"]
    )
    assert grounding_violations(ok, facts, taxonomy) == []


async def test_valid_llm_answer_is_accepted_and_usage_recorded(facts, taxonomy):
    llm = ScriptedLLM([answer()])
    with usage_scope() as records:
        result = await ExplanationGenerator(llm, taxonomy).generate(facts)
    assert result.source == "llm"
    assert result.attempts == 1
    assert result.prompt_version == "match_explanation/v1"
    assert records[0].success and records[0].input_tokens == 120
    assert records[0].prompt_version == "match_explanation/v1"


async def test_invalid_json_then_schema_error_then_success(facts, taxonomy):
    llm = ScriptedLLM(
        ["not json", json.dumps({"summary": "short"}), "```json\n" + answer() + "\n```"]
    )
    with usage_scope() as records:
        result = await ExplanationGenerator(llm, taxonomy, validation_retries=2).generate(facts)
    assert result.source == "llm"
    assert result.attempts == 3
    assert "does not contain a JSON object" in llm.requests[1].user
    assert "summary" in llm.requests[2].user
    assert [r.success for r in records] == [False, False, True]


async def test_exhausted_retries_fall_back_to_template(facts, taxonomy):
    llm = ScriptedLLM([answer(skills_mentioned=["Scala"])] * 2)
    result = await ExplanationGenerator(llm, taxonomy, validation_retries=1).generate(facts)
    assert result.source == "template_fallback"
    assert result.attempts == 2
    assert result.violations
    assert result.explanation == render_explanation(facts)


async def test_provider_error_falls_back(facts, taxonomy):
    llm = ScriptedLLM([ProviderError("boom")])
    with usage_scope() as records:
        result = await ExplanationGenerator(llm, taxonomy).generate(facts)
    assert result.source == "template_fallback"
    assert records[0].success is False


async def test_offline_provider_is_deterministic(facts, taxonomy):
    gen = ExplanationGenerator(OfflineTemplateProvider(), taxonomy)
    a, b = await gen.generate(facts), await gen.generate(facts)
    assert a.source == "offline_template"
    assert a.explanation == b.explanation


def test_prompt_loader_and_rendering():
    prompt = load_prompt("match_explanation", "v1")
    assert prompt.version_id == "match_explanation/v1"
    assert "never" in prompt.system.lower()
    assert '"x": 1' in prompt.render_user(facts_json='{"x": 1}')
    with pytest.raises(ValueError, match="Unfilled"):
        prompt.render_user()


def test_json_extraction_helpers():
    assert extract_json_object('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json_object("[1, 2]")
    with pytest.raises(ValueError):
        extract_json_object("{broken")
    assert is_transient(type("RateLimitError", (Exception,), {})())
    assert not is_transient(ValueError())


def test_usage_estimates():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd" * 10) == 10
    assert estimate_cost("gpt-4o-mini", 1_000_000, 0) == 0.15
    assert estimate_cost("unknown", 10, 10) is None


class _Transient(Exception):
    pass


_Transient.__name__ = "APITimeoutError"


def _openai_client(script):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
            model="gpt-4o-mini-2024",
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


async def test_openai_provider_retries_transient_errors():
    client, calls = _openai_client([_Transient(), '{"ok": true}'])
    provider = OpenAIProvider(api_key=None, model="gpt-4o-mini", timeout=5, client=client)
    resp = await provider.complete(LLMRequest(system="s", user="u"))
    assert resp.text == '{"ok": true}'
    assert (resp.input_tokens, resp.output_tokens, resp.model) == (11, 7, "gpt-4o-mini-2024")
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["temperature"] == 0


async def test_openai_provider_wraps_permanent_errors():
    client, _ = _openai_client([ValueError("bad request")])
    provider = OpenAIProvider(api_key=None, model="m", timeout=5, client=client)
    with pytest.raises(ProviderError):
        await provider.complete(LLMRequest(system="s", user="u"))
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key=None, model="m", timeout=5)


async def test_anthropic_provider():
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"a": 1}')],
            usage=SimpleNamespace(input_tokens=5, output_tokens=3),
            model="claude-sonnet-4-5",
        )

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider = AnthropicProvider(api_key=None, model="claude-sonnet-4-5", timeout=5, client=client)
    resp = await provider.complete(LLMRequest(system="sys", user="usr", max_output_tokens=100))
    assert resp.text == '{"a": 1}' and resp.input_tokens == 5
    assert calls[0]["system"] == "sys" and calls[0]["max_tokens"] == 100
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(api_key=None, model="m", timeout=5)

    async def failing(**kwargs):
        raise RuntimeError("down")

    broken = AnthropicProvider(
        api_key=None,
        model="m",
        timeout=5,
        client=SimpleNamespace(messages=SimpleNamespace(create=failing)),
    )
    with pytest.raises(ProviderError):
        await broken.complete(LLMRequest(system="s", user="u"))


def test_provider_factory_defaults_to_offline():
    assert build_llm_provider(make_settings()).name == "offline"
    with pytest.raises(ProviderError):
        build_llm_provider(make_settings(llm_provider="openai"))
    with pytest.raises(ProviderError):
        build_llm_provider(make_settings(llm_provider="anthropic"))
