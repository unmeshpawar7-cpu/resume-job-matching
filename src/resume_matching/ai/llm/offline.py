"""``OfflineTemplateProvider`` - the default, deterministic, NON-LLM provider.

It renders the explanation from the computed facts with fixed templates
(:mod:`resume_matching.ai.narrative`). There is no language model involved; it exists so
the service runs, demos and tests without API keys, and it produces schema-valid output
through exactly the same validation path as the real providers.
"""

from __future__ import annotations

import json

from resume_matching.ai.contracts import ExplanationFacts
from resume_matching.ai.llm.base import LLMRequest, LLMResponse
from resume_matching.ai.narrative import render_explanation
from resume_matching.ai.usage import estimate_tokens


class OfflineTemplateProvider:
    name = "offline"
    model = "offline-template-v1"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        facts = ExplanationFacts.model_validate(request.facts)
        text = json.dumps(render_explanation(facts).model_dump(mode="json"))
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=estimate_tokens(request.system) + estimate_tokens(request.user),
            output_tokens=estimate_tokens(text),
        )
