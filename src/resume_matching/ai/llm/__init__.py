"""LLM providers selected by ``LLM_PROVIDER`` (offline | openai | anthropic)."""

from __future__ import annotations

from resume_matching.ai.llm.base import LLMProvider, LLMRequest, LLMResponse
from resume_matching.ai.llm.offline import OfflineTemplateProvider
from resume_matching.core.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        from resume_matching.ai.llm.openai import OpenAIProvider

        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAIProvider(
            api_key=key,
            model=settings.openai_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if settings.llm_provider == "anthropic":
        from resume_matching.ai.llm.anthropic import AnthropicProvider

        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        return AnthropicProvider(
            api_key=key,
            model=settings.anthropic_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return OfflineTemplateProvider()


__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "OfflineTemplateProvider",
    "build_llm_provider",
]
