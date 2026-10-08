"""Embedding providers: deterministic hashing (default) and OpenAI."""

from __future__ import annotations

from resume_matching.ai.embeddings.base import EmbeddingProvider
from resume_matching.ai.embeddings.hashing import HashingEmbeddingProvider
from resume_matching.core.config import Settings


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        from resume_matching.ai.embeddings.openai import OpenAIEmbeddingProvider

        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAIEmbeddingProvider(
            api_key=key,
            model=settings.openai_embedding_model,
            dim=settings.embedding_dim,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return HashingEmbeddingProvider(settings.embedding_dim)


__all__ = ["EmbeddingProvider", "HashingEmbeddingProvider", "build_embedding_provider"]
