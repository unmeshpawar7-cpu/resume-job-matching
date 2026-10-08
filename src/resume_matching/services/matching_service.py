"""Match analysis and candidate ranking.

The score is computed by the deterministic engine; the explanation generator only ever
receives the computed facts. Results are idempotent per (resume, job, scoring_version).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.ai.contracts import build_facts
from resume_matching.ai.explanation import ExplanationResult, template_result
from resume_matching.ai.usage import usage_scope
from resume_matching.core.errors import NotFoundError
from resume_matching.db.models import Job, MatchResult, Resume, User
from resume_matching.db.types import utcnow
from resume_matching.domain.job_analysis import JobAnalysis
from resume_matching.domain.profile import ResumeProfile
from resume_matching.domain.ranking import RankEntry, rank, top_reasons
from resume_matching.domain.scoring import MatchComputation, ScoringInput, score_match
from resume_matching.repositories.jobs import JobRepository
from resume_matching.repositories.matches import AIUsageRepository, MatchRepository
from resume_matching.repositories.resumes import ResumeRepository
from resume_matching.services.container import AppContainer
from resume_matching.services.job_service import job_embedding_text
from resume_matching.services.resume_service import embedding_input

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RankingResult:
    job_id: str
    scoring_version: str
    considered: int
    newly_computed: int
    ranked: list[tuple[RankEntry, MatchResult, Resume]]


def _explanation_payload(result: ExplanationResult) -> dict:
    payload = result.explanation.to_json_dict()
    payload.update(
        {
            "source": result.source,
            "provider": result.provider,
            "model": result.model,
            "promptVersion": result.prompt_version,
            "attempts": result.attempts,
            "violations": result.violations,
        }
    )
    return payload


class MatchingService:
    def __init__(self, session: AsyncSession, container: AppContainer) -> None:
        self.session = session
        self.c = container
        self.resumes = ResumeRepository(session)
        self.jobs = JobRepository(session)
        self.matches = MatchRepository(session)
        self.usage = AIUsageRepository(session)

    # ------------------------------------------------------------------ helpers
    async def _ensure_embeddings(self, resume: Resume, job: Job) -> None:
        """Re-embed with the current provider if a row was embedded by another model."""
        model_id = self.c.embedder.model_id
        if job.embedding_model != model_id or job.embedding is None:
            [job.embedding] = await self.c.embedder.embed(
                [job_embedding_text(job.title, job.description)]
            )
            job.embedding_model = model_id
        if resume.embedding_model != model_id:
            vectors = await self.c.embedder.embed(
                [embedding_input(s.text) for s in resume.sections]
            )
            for section, vector in zip(resume.sections, vectors, strict=True):
                section.embedding = vector
            resume.embedding_model = model_id
            await self.c.vector_store.upsert(
                self.session,
                resume.id,
                {s.section_type: s.embedding or [] for s in resume.sections},
            )

    def _compute(self, resume: Resume, job: Job) -> MatchComputation:
        data = ScoringInput(
            profile=ResumeProfile.model_validate(resume.profile),
            job=JobAnalysis.model_validate(job.analysis),
            resume_text="\n\n".join(s.text for s in resume.sections),
            section_vectors={s.section_type: s.embedding for s in resume.sections if s.embedding},
            job_vector=job.embedding,
            embedding_provider=self.c.embedder.name,
        )
        return score_match(data, self.c.taxonomy, self.c.scoring, self.c.scoring_version)

    async def _load(self, resume_id: str, job_id: str) -> tuple[Resume, Job]:
        resume = await self.resumes.get(resume_id, with_sections=True)
        if resume is None:
            raise NotFoundError(f"Resume {resume_id} not found")
        job = await self.jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return resume, job

    @staticmethod
    def _apply(
        match: MatchResult, computation: MatchComputation, explanation: ExplanationResult
    ) -> None:
        match.overall_score = computation.overall_score
        match.result = computation.to_json_dict()
        match.explanation = _explanation_payload(explanation)
        match.explanation_source = explanation.source
        match.prompt_version = explanation.prompt_version
        match.llm_provider = explanation.provider
        match.llm_model = explanation.model
        match.updated_at = utcnow()

    # ------------------------------------------------------------------ analyze
    async def analyze(
        self, resume_id: str, job_id: str, *, force: bool, user: User
    ) -> tuple[MatchResult, bool]:
        """Returns ``(match, created)``. ``created`` is False when an existing result for the
        current scoring version was returned (or recomputed in place with ``force``)."""
        version = self.c.scoring_version
        existing = await self.matches.find(resume_id, job_id, version)
        if existing is not None and not force:
            if existing.explanation_source == "deferred_template" and self.c.llm.name != "offline":
                # Batch-ranked result: attach the LLM narrative now. The score is untouched.
                computation = MatchComputation.model_validate(existing.result)
                explanation, records = await self._explain(computation)
                self._apply(existing, computation, explanation)
                self.usage.add_records(records, user_id=user.id, match_id=existing.id)
                await self.session.commit()
            return existing, False

        resume, job = await self._load(resume_id, job_id)
        await self._ensure_embeddings(resume, job)
        computation = self._compute(resume, job)
        match = existing or MatchResult(
            resume_id=resume.id, job_id=job.id, scoring_version=version, created_by=user.id
        )
        explanation, records = await self._explain(computation)
        self._apply(match, computation, explanation)
        if existing is None:
            try:
                await self.matches.add(match)
            except IntegrityError:  # concurrent request created it first
                await self.session.rollback()
                winner = await self.matches.find(resume_id, job_id, version)
                if winner is None:  # pragma: no cover - defensive
                    raise
                return winner, False
        self.usage.add_records(records, user_id=user.id, match_id=match.id)
        await self.session.commit()
        logger.info(
            "match_analyzed",
            extra={
                "match_id": match.id,
                "score": computation.overall_score,
                "scoring_version": version,
                "explanation_source": explanation.source,
                "forced": force,
            },
        )
        return match, existing is None

    async def _explain(
        self, computation: MatchComputation, user: User, match_id: str | None
    ) -> ExplanationResult:
        with usage_scope() as records:
            result = await self.c.explainer.generate(build_facts(computation, self.c.taxonomy))
        self._pending_usage = records
        if match_id is not None:
            self.usage.add_records(records, user_id=user.id, match_id=match_id)
            self._pending_usage = []
        return result

    _pending_usage: list = []

    async def get(self, match_id: str) -> MatchResult:
        match = await self.matches.get(match_id)
        if match is None:
            raise NotFoundError(f"Match result {match_id} not found")
        return match

    # ------------------------------------------------------------------ ranking
    async def ranking(self, job_id: str, min_score: float | None, user: User) -> RankingResult:
        job = await self.jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        version = self.c.scoring_version
        if job.embedding_model != self.c.embedder.model_id or job.embedding is None:
            [job.embedding] = await self.c.embedder.embed(
                [job_embedding_text(job.title, job.description)]
            )
            job.embedding_model = self.c.embedder.model_id

        pool = self.c.settings.ranking_candidate_pool
        if await self.resumes.count() > pool:
            hits = await self.c.vector_store.search(self.session, job.embedding or [], pool)
            resumes = await self.resumes.list_with_sections([rid for rid, _ in hits])
        else:
            resumes = await self.resumes.list_with_sections()

        existing = await self.matches.for_job(job.id, version)
        computed = 0
        for resume in resumes:
            if resume.id in existing:
                continue
            await self._ensure_embeddings(resume, job)
            computation = self._compute(resume, job)
            # Batch results get the deterministic narrative; the LLM narrative is attached
            # lazily when someone opens the match via POST /api/matching/analyze.
            explanation = template_result(
                build_facts(computation, self.c.taxonomy), "deferred_template"
            )
            explanation.prompt_version = self.c.explainer.prompt_version
            match = MatchResult(
                resume_id=resume.id, job_id=job.id, scoring_version=version, created_by=user.id
            )
            self._apply(match, computation, explanation)
            try:
                async with self.session.begin_nested():
                    self.session.add(match)
            except IntegrityError:  # pragma: no cover - concurrent ranking request
                continue
            existing[resume.id] = match
            computed += 1
        await self.session.commit()

        by_id = {r.id: r for r in resumes}
        entries = [
            RankEntry(
                resume_id=rid,
                created_at=by_id[rid].created_at,
                computation=MatchComputation.model_validate(m.result),
            )
            for rid, m in existing.items()
            if rid in by_id
        ]
        ranked = rank(entries, min_score)
        logger.info(
            "ranking_computed",
            extra={"job_id": job.id, "candidates": len(resumes), "newly_computed": computed},
        )
        return RankingResult(
            job_id=job.id,
            scoring_version=version,
            considered=len(resumes),
            newly_computed=computed,
            ranked=[(e, existing[e.resume_id], by_id[e.resume_id]) for e in ranked],
        )


__all__ = ["MatchingService", "RankingResult", "top_reasons"]
