"""Application container: long-lived, shared collaborators built once at startup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from resume_matching.ai.embeddings import EmbeddingProvider
from resume_matching.ai.explanation import ExplanationGenerator
from resume_matching.ai.llm import LLMProvider
from resume_matching.core.config import ScoringSettings, Settings
from resume_matching.core.rate_limit import TokenBucketLimiter
from resume_matching.domain.taxonomy import SkillTaxonomy
from resume_matching.repositories.vector_store import VectorStore


def utc_today() -> date:
    return datetime.now(UTC).date()


@dataclass
class AppContainer:
    settings: Settings
    scoring: ScoringSettings
    taxonomy: SkillTaxonomy
    embedder: EmbeddingProvider
    llm: LLMProvider
    explainer: ExplanationGenerator
    vector_store: VectorStore
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    analyze_limiter: TokenBucketLimiter
    login_limiter: TokenBucketLimiter
    today: Callable[[], date] = field(default=utc_today)

    @property
    def scoring_version(self) -> str:
        return self.scoring.scoring_version(self.embedder.model_id, self.taxonomy.version)
