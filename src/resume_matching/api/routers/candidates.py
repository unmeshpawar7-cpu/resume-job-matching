from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Query

from resume_matching.api.deps import ContainerDep, CurrentUser, PageDep, SessionDep
from resume_matching.api.mappers import ranking_item
from resume_matching.schemas.common import Envelope, ok
from resume_matching.schemas.matching import RankingPage
from resume_matching.services.matching_service import MatchingService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.get(
    "/ranking",
    response_model=Envelope[RankingPage],
    summary="Rank candidates for a job",
    description="Computes any missing matches for the current scoring version (batch results "
    "use the deterministic narrative), then ranks by score with deterministic tie-breaks "
    "(required coverage, semantic similarity, upload time). Above RANKING_CANDIDATE_POOL "
    "resumes, the pool is pre-selected by vector similarity.",
)
async def ranking(
    session: SessionDep,
    container: ContainerDep,
    user: CurrentUser,
    paging: PageDep,
    job_id: Annotated[str, Query(min_length=1, max_length=36)],
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
) -> dict:
    result = await MatchingService(session, container).ranking(job_id, min_score, user)
    total = len(result.ranked)
    start = (paging.page - 1) * paging.page_size
    window = result.ranked[start : start + paging.page_size]
    items = [
        ranking_item(start + i + 1, entry, match, resume)
        for i, (entry, match, resume) in enumerate(window)
    ]
    return ok(
        RankingPage(
            job_id=result.job_id,
            scoring_version=result.scoring_version,
            candidates_considered=result.considered,
            newly_computed=result.newly_computed,
            items=items,
            page=paging.page,
            page_size=paging.page_size,
            total_count=total,
            total_pages=math.ceil(total / paging.page_size) if total else 0,
        )
    )
