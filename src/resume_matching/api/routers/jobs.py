from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from resume_matching.api.deps import ContainerDep, CurrentUser, PageDep, SessionDep
from resume_matching.api.mappers import job_out, job_summary
from resume_matching.schemas.common import Envelope, Page, ok
from resume_matching.schemas.jobs import JobCreate, JobOut, JobSummary
from resume_matching.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[JobOut],
    summary="Create a job description",
    description="Analyses the JD: required vs nice-to-have skills (explicit lists win, else "
    "cue phrases such as 'must have', 'nice to have', 'a plus'), minimum years, seniority.",
)
async def create_job(
    body: JobCreate, session: SessionDep, container: ContainerDep, user: CurrentUser
) -> JSONResponse:
    job = await JobService(session, container).create(body, user)
    return JSONResponse(
        ok(job_out(job)), status_code=201, headers={"Location": f"/api/jobs/{job.id}"}
    )


@router.get("", response_model=Envelope[Page[JobSummary]], summary="List jobs")
async def list_jobs(
    session: SessionDep, container: ContainerDep, _: CurrentUser, paging: PageDep
) -> dict:
    rows, total = await JobService(session, container).list(paging.page, paging.page_size)
    return ok(
        Page[JobSummary].build([job_summary(j) for j in rows], paging.page, paging.page_size, total)
    )


@router.get("/{job_id}", response_model=Envelope[JobOut], summary="Get a job and its analysis")
async def get_job(
    job_id: str, session: SessionDep, container: ContainerDep, _: CurrentUser
) -> dict:
    return ok(job_out(await JobService(session, container).get(job_id)))
