from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.ai.usage import UsageRecord
from resume_matching.db.models import AIUsage, MatchResult


class MatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, match_id: str) -> MatchResult | None:
        return await self.session.get(MatchResult, match_id)

    async def find(self, resume_id: str, job_id: str, scoring_version: str) -> MatchResult | None:
        stmt = select(MatchResult).where(
            MatchResult.resume_id == resume_id,
            MatchResult.job_id == job_id,
            MatchResult.scoring_version == scoring_version,
        )
        return await self.session.scalar(stmt)

    async def for_job(self, job_id: str, scoring_version: str) -> dict[str, MatchResult]:
        stmt = select(MatchResult).where(
            MatchResult.job_id == job_id, MatchResult.scoring_version == scoring_version
        )
        return {m.resume_id: m for m in (await self.session.scalars(stmt)).all()}

    async def add(self, match: MatchResult) -> MatchResult:
        self.session.add(match)
        await self.session.flush()
        return match


class AIUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_records(
        self,
        records: Iterable[UsageRecord],
        *,
        user_id: str | None = None,
        match_id: str | None = None,
    ) -> None:
        for r in records:
            self.session.add(
                AIUsage(
                    operation=r.operation,
                    provider=r.provider,
                    model=r.model,
                    prompt_version=r.prompt_version,
                    match_id=match_id,
                    user_id=user_id,
                    attempt=r.attempt,
                    latency_ms=r.latency_ms,
                    input_tokens=r.input_tokens,
                    output_tokens=r.output_tokens,
                    estimated_cost_usd=r.estimated_cost_usd,
                    success=r.success,
                    error_type=r.error_type,
                )
            )
