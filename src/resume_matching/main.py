"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI

from resume_matching import __version__
from resume_matching.ai.embeddings import EmbeddingProvider, build_embedding_provider
from resume_matching.ai.explanation import ExplanationGenerator
from resume_matching.ai.llm import LLMProvider, build_llm_provider
from resume_matching.api.errors import register_exception_handlers
from resume_matching.api.middleware import RequestContextMiddleware
from resume_matching.api.routers import auth, candidates, health, jobs, matching, resumes
from resume_matching.core.config import (
    ScoringSettings,
    Settings,
    get_scoring_settings,
    get_settings,
)
from resume_matching.core.logging import configure_logging
from resume_matching.core.rate_limit import TokenBucketLimiter
from resume_matching.db.session import create_all, create_engine, create_sessionmaker
from resume_matching.domain.taxonomy import cached_taxonomy
from resume_matching.repositories.resumes import ResumeRepository
from resume_matching.repositories.vector_store import InMemoryVectorStore, PgVectorStore
from resume_matching.services.auth_service import AuthService
from resume_matching.services.container import AppContainer, utc_today

logger = logging.getLogger(__name__)

DESCRIPTION = """
Explainable resume <-> job-description matching.

**The score is deterministic + semantic; the LLM only writes the narrative and never
changes the number.** Every result carries a component breakdown, matched/missing skills,
`scoringVersion` and `promptVersion`.

Authenticate with `POST /api/auth/token` and send `Authorization: Bearer <token>`.
"""


def build_container(
    settings: Settings,
    scoring: ScoringSettings,
    *,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
    today: Callable[[], date] | None = None,
) -> AppContainer:
    taxonomy = cached_taxonomy(str(settings.taxonomy_path))
    llm = llm or build_llm_provider(settings)
    engine = create_engine(settings.database_url)
    return AppContainer(
        settings=settings,
        scoring=scoring,
        taxonomy=taxonomy,
        embedder=embedder or build_embedding_provider(settings),
        llm=llm,
        explainer=ExplanationGenerator(
            llm,
            taxonomy,
            validation_retries=settings.llm_validation_retries,
            max_output_tokens=settings.llm_max_output_tokens,
        ),
        vector_store=InMemoryVectorStore() if settings.is_sqlite else PgVectorStore(),
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        analyze_limiter=TokenBucketLimiter(
            settings.analyze_rate_limit_per_minute, settings.analyze_rate_limit_burst
        ),
        login_limiter=TokenBucketLimiter(
            settings.login_rate_limit_per_minute, settings.login_rate_limit_burst
        ),
        today=today or utc_today,
    )


def create_app(
    settings: Settings | None = None,
    scoring: ScoringSettings | None = None,
    *,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
    today: Callable[[], date] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    scoring = scoring or get_scoring_settings()
    configure_logging(settings.log_level, settings.log_json)
    container = build_container(settings, scoring, llm=llm, embedder=embedder, today=today)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.db_create_all:
            await create_all(container.engine)
        async with container.sessionmaker() as session:
            if isinstance(container.vector_store, InMemoryVectorStore):
                container.vector_store.load(await ResumeRepository(session).all_section_vectors())
            if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
                await AuthService(session, settings).ensure_admin(
                    settings.bootstrap_admin_email,
                    settings.bootstrap_admin_password.get_secret_value(),
                )
        logger.info(
            "startup",
            extra={
                "llm_provider": container.llm.name,
                "embedding_model": container.embedder.model_id,
                "scoring_version": container.scoring_version,
                "taxonomy_version": container.taxonomy.version,
            },
        )
        yield
        await container.engine.dispose()

    app = FastAPI(
        title="Resume-Job Matching API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.container = container
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    for router in (health, auth, resumes, jobs, matching, candidates):
        app.include_router(router.router)
    return app


def app_factory() -> FastAPI:  # pragma: no cover - used by uvicorn --factory
    return create_app()
