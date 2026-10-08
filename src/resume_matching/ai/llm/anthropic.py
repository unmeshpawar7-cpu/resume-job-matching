"""Anthropic Messages API provider (optional extra: ``pip install .[anthropic]``)."""

from __future__ import annotations

import asyncio
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from resume_matching.ai.llm.base import LLMRequest, LLMResponse, is_transient
from resume_matching.ai.usage import estimate_tokens
from resume_matching.core.errors import ProviderError


class AnthropicProvider:
    name = "anthropic"

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
                raise ProviderError("ANTHROPIC_API_KEY is required for LLM_PROVIDER=anthropic")
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ProviderError(
                    "Install the 'anthropic' extra: pip install .[anthropic]"
                ) from exc
            client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=0)
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
                self._client.messages.create(
                    model=self.model,
                    system=request.system,
                    messages=[{"role": "user", "content": request.user}],
                    max_tokens=request.max_output_tokens,
                    temperature=0,
                ),
                timeout=self._timeout,
            )

        try:
            response = await _call()
        except Exception as exc:
            raise ProviderError(f"Anthropic request failed ({type(exc).__name__})") from exc
        text = "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", "text") == "text"
        )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "input_tokens", None)
            or estimate_tokens(request.system + request.user),
            output_tokens=getattr(usage, "output_tokens", None) or estimate_tokens(text),
        )
