"""OpenAI chat-completions provider (optional extra: ``pip install .[openai]``)."""

from __future__ import annotations

import asyncio
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from resume_matching.ai.llm.base import LLMRequest, LLMResponse, is_transient
from resume_matching.ai.usage import estimate_tokens
from resume_matching.core.errors import ProviderError


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout: float,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ProviderError("OPENAI_API_KEY is required for LLM_PROVIDER=openai")
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ProviderError("Install the 'openai' extra: pip install .[openai]") from exc
            client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        self._client = client
        self.model = model
        self._timeout = timeout
        self._max_retries = max_retries

    async def complete(self, request: LLMRequest) -> LLMResponse:
        @retry(
            retry=retry_if_exception(is_transient),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )
        async def _call() -> Any:
            return await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": request.system},
                        {"role": "user", "content": request.user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=request.max_output_tokens,
                ),
                timeout=self._timeout,
            )

        try:
            response = await _call()
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed ({type(exc).__name__})") from exc
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "prompt_tokens", None)
            or estimate_tokens(request.system + request.user),
            output_tokens=getattr(usage, "completion_tokens", None) or estimate_tokens(text),
        )
