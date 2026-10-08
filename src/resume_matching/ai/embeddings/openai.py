"""OpenAI embeddings (optional extra: ``pip install .[openai]``)."""

from __future__ import annotations

import time
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from resume_matching.ai.llm.base import is_transient
from resume_matching.ai.usage import estimate_tokens, record_usage
from resume_matching.core.errors import ProviderError


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dim: int,
        timeout: float,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ProviderError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai")
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ProviderError("Install the 'openai' extra: pip install .[openai]") from exc
            client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        self._client = client
        self.model = model
        self.dim = dim
        self.model_id = f"openai-{model}-{dim}"
        self._max_retries = max_retries

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        @retry(
            retry=retry_if_exception(is_transient),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )
        async def _call() -> Any:
            return await self._client.embeddings.create(
                model=self.model, input=texts, dimensions=self.dim
            )

        started = time.perf_counter()
        try:
            response = await _call()
        except Exception as exc:
            record_usage(
                operation="embedding", provider=self.name, model=self.model,
                latency_ms=(time.perf_counter() - started) * 1000,
                input_tokens=sum(estimate_tokens(t) for t in texts), output_tokens=0,
                success=False, error_type=type(exc).__name__,
            )  # fmt: skip
            raise ProviderError("Embedding request failed") from exc
        usage = getattr(response, "usage", None)
        record_usage(
            operation="embedding", provider=self.name, model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=getattr(usage, "prompt_tokens", None)
            or sum(estimate_tokens(t) for t in texts),
            output_tokens=0, success=True,
        )  # fmt: skip
        return [list(item.embedding) for item in response.data]
