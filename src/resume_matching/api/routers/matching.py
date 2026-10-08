from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from resume_matching.api.deps import ContainerDep, CurrentUser, SessionDep
from resume_matching.api.mappers import match_out
from resume_matching.schemas.common import Envelope, ok
from resume_matching.schemas.matching import AnalyzeRequest, MatchOut
from resume_matching.services.matching_service import MatchingService

router = APIRouter(prefix="/api/matching", tags=["matching"])


@router.post(
    "/analyze",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[MatchOut],
    responses={200: {"description": "Existing result for this scoring version returned"}},
    summary="Score a resume against a job",
    description="Deterministic + semantic score with a full breakdown; the LLM only writes "
    "`explanation` from the computed facts. Idempotent per resume + job + scoring_version: "
    "201 when a new result is created, 200 when an existing one is returned (or recomputed "
    "in place with `force=true`). Rate limited per user (429).",
)
async def analyze(
    body: AnalyzeRequest, session: SessionDep, container: ContainerDep, user: CurrentUser
) -> JSONResponse:
    container.analyze_limiter.check(user.id)
    match, created = await MatchingService(session, container).analyze(
        body.resume_id, body.job_id, force=body.force, user=user
    )
    return JSONResponse(
        ok(match_out(match)),
        status_code=201 if created else 200,
        headers={"Location": f"/api/matching/{match.id}"},
    )


@router.get("/{match_id}", response_model=Envelope[MatchOut], summary="Get a match result")
async def get_match(
    match_id: str, session: SessionDep, container: ContainerDep, _: CurrentUser
) -> dict:
    return ok(match_out(await MatchingService(session, container).get(match_id)))
