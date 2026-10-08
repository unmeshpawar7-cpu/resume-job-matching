"""Explanation pipeline: facts -> prompt -> LLM -> validate -> ground -> (retry) -> fallback.

The LLM never sees resume text and never produces the score. Its output is accepted only if

1. it parses as JSON and validates against :class:`MatchExplanation`;
2. every entry in ``skills_mentioned`` resolves to a skill in ``facts.allowed_skills``;
3. no taxonomy skill outside ``allowed_skills`` appears anywhere in the prose;
4. every percentage / "NN/100" figure in the prose equals the computed overall score or a
   component score.

On failure the errors are fed back for a bounded number of retries; after that (or on a
provider error) the deterministic template is used and ``source="template_fallback"``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from resume_matching.ai.contracts import ExplanationFacts, ExplanationSource, MatchExplanation
from resume_matching.ai.llm.base import LLMProvider, LLMRequest, extract_json_object
from resume_matching.ai.narrative import render_explanation
from resume_matching.ai.prompts import PromptTemplate, load_prompt
from resume_matching.ai.usage import record_usage
from resume_matching.core.errors import ProviderError
from resume_matching.domain.taxonomy import SkillTaxonomy

logger = logging.getLogger(__name__)

PROMPT_NAME = "match_explanation"
PROMPT_VERSION = "v1"
#: Categories excluded from the free-text scan: generic practice words ("mentoring",
#: "code review") are ordinary English in a narrative and not technology claims.
_TEXT_SCAN_EXCLUDED_CATEGORIES = frozenset({"practice"})
_NUMBER_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|/\s*100\b|\s+percent\b)", re.IGNORECASE)


@dataclass(slots=True)
class ExplanationResult:
    explanation: MatchExplanation
    source: ExplanationSource
    provider: str
    model: str
    prompt_version: str
    attempts: int
    violations: list[str] = field(default_factory=list)


def grounding_violations(
    explanation: MatchExplanation, facts: ExplanationFacts, taxonomy: SkillTaxonomy
) -> list[str]:
    allowed = {s.casefold() for s in facts.allowed_skills}
    problems: list[str] = []
    for raw in explanation.skills_mentioned:
        canonical = taxonomy.canonical(raw) or raw
        if canonical.casefold() not in allowed:
            problems.append(f"skills_mentioned contains '{raw}', which is not in allowedSkills")
    prose = "\n".join([explanation.summary, *explanation.strengths, *explanation.gaps])
    for name in sorted(taxonomy.find_names(prose)):
        if name.casefold() in allowed:
            continue
        if taxonomy.category(name) in _TEXT_SCAN_EXCLUDED_CATEGORIES:
            continue
        problems.append(f"text mentions '{name}', which is not in allowedSkills")
    valid_numbers = {round(facts.overall_score, 1)} | {
        round(c.score, 1) for c in facts.components if c.score is not None
    }
    for match in _NUMBER_RE.finditer(prose):
        value = round(float(match.group(1)), 1)
        if not any(abs(value - v) <= 0.51 for v in valid_numbers):
            problems.append(
                f"text states '{match.group(0)}' but the computed score is {facts.overall_score:g}"
            )
    return problems


def template_result(facts: ExplanationFacts, source: ExplanationSource) -> ExplanationResult:
    return ExplanationResult(
        explanation=render_explanation(facts),
        source=source,
        provider="template",
        model="offline-template-v1",
        prompt_version=f"{PROMPT_NAME}/{PROMPT_VERSION}",
        attempts=0,
    )


class ExplanationGenerator:
    def __init__(
        self,
        provider: LLMProvider,
        taxonomy: SkillTaxonomy,
        *,
        validation_retries: int = 2,
        max_output_tokens: int = 700,
        prompt: PromptTemplate | None = None,
    ) -> None:
        self.provider = provider
        self.taxonomy = taxonomy
        self.validation_retries = validation_retries
        self.max_output_tokens = max_output_tokens
        self.prompt = prompt or load_prompt(PROMPT_NAME, PROMPT_VERSION)

    @property
    def prompt_version(self) -> str:
        return self.prompt.version_id

    async def generate(self, facts: ExplanationFacts) -> ExplanationResult:
        facts_dict = facts.to_json_dict()
        base_user = self.prompt.render_user(facts_json=json.dumps(facts_dict, indent=2))
        user = base_user
        last_problems: list[str] = []
        attempts = 0
        for attempt in range(1, self.validation_retries + 2):
            attempts = attempt
            request = LLMRequest(
                system=self.prompt.system,
                user=user,
                facts=facts_dict,
                max_output_tokens=self.max_output_tokens,
            )
            started = time.perf_counter()
            try:
                response = await self.provider.complete(request)
            except ProviderError as exc:
                self._record(started, 0, 0, attempt, False, type(exc.__cause__ or exc).__name__)
                logger.warning("explanation_provider_failed", extra={"attempt": attempt})
                result = template_result(facts, "template_fallback")
                result.violations = [str(exc)]
                result.attempts = attempt
                return result
            problems = self._check(response.text, facts)
            self._record(
                started,
                response.input_tokens,
                response.output_tokens,
                attempt,
                not problems,
                None if not problems else "validation_failed",
                model=response.model,
            )
            if not problems:
                return ExplanationResult(
                    explanation=MatchExplanation.model_validate(extract_json_object(response.text)),
                    source="offline_template" if self.provider.name == "offline" else "llm",
                    provider=self.provider.name,
                    model=response.model,
                    prompt_version=self.prompt_version,
                    attempts=attempt,
                )
            last_problems = problems
            logger.info(
                "explanation_rejected", extra={"attempt": attempt, "problems": problems[:5]}
            )
            user = (
                base_user
                + "\n\nYour previous answer was rejected for these reasons:\n- "
                + "\n- ".join(problems[:10])
                + "\nReturn a corrected JSON object only."
            )
        result = template_result(facts, "template_fallback")
        result.violations = last_problems
        result.attempts = attempts
        result.prompt_version = self.prompt_version
        return result

    def _check(self, text: str, facts: ExplanationFacts) -> list[str]:
        try:
            payload = extract_json_object(text)
            explanation = MatchExplanation.model_validate(payload)
        except ValueError as exc:  # includes pydantic.ValidationError
            if isinstance(exc, ValidationError):
                return [
                    f"{'.'.join(str(p) for p in e['loc']) or 'root'}: {e['msg']}"
                    for e in exc.errors()
                ]
            return [str(exc)]
        return grounding_violations(explanation, facts, self.taxonomy)

    def _record(
        self,
        started: float,
        input_tokens: int,
        output_tokens: int,
        attempt: int,
        success: bool,
        error_type: str | None,
        model: str | None = None,
    ) -> None:
        record_usage(
            operation="match_explanation",
            provider=self.provider.name,
            model=model or self.provider.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
            prompt_version=self.prompt_version,
            error_type=error_type,
            attempt=attempt,
        )
