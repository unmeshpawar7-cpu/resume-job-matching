from __future__ import annotations

from fastapi import APIRouter, File, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse

from resume_matching.api.deps import ContainerDep, CurrentUser, PageDep, SessionDep
from resume_matching.api.mappers import resume_out, resume_summary
from resume_matching.core.errors import PayloadTooLargeError, UnprocessableError
from resume_matching.schemas.common import Envelope, Page, ok
from resume_matching.schemas.resumes import ResumeOut, ResumeSummary
from resume_matching.services.resume_service import ResumeService

router = APIRouter(prefix="/api/resumes", tags=["resumes"])
_MULTIPART_OVERHEAD = 64 * 1024
_CHUNK = 64 * 1024


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    """Read the upload in chunks and stop as soon as it exceeds ``limit`` (413)."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(f"File exceeds the {limit // 1024} KiB limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResumeOut],
    summary="Upload and parse a resume (.pdf, .docx, .txt)",
    description="Validates extension + magic bytes (415), size (413), extracts text, detects "
    "sections, extracts skills/experience/titles and embeds the scored sections. "
    "The same file uploaded twice returns 409.",
)
async def upload_resume(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    user: CurrentUser,
    file: UploadFile = File(..., description="Resume file"),
) -> JSONResponse:
    limit = container.settings.max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + _MULTIPART_OVERHEAD:
        raise PayloadTooLargeError(f"File exceeds the {limit // 1024} KiB limit")
    data = await _read_limited(file, limit)
    if not data:
        raise UnprocessableError("The uploaded file is empty")
    resume = await ResumeService(session, container).upload(file.filename or "resume", data, user)
    return JSONResponse(
        ok(resume_out(resume)),
        status_code=201,
        headers={"Location": f"/api/resumes/{resume.id}"},
    )


@router.get("", response_model=Envelope[Page[ResumeSummary]], summary="List resumes")
async def list_resumes(
    session: SessionDep, container: ContainerDep, _: CurrentUser, paging: PageDep
) -> dict:
    rows, total = await ResumeService(session, container).list(paging.page, paging.page_size)
    page = Page[ResumeSummary].build(
        [resume_summary(r) for r in rows], paging.page, paging.page_size, total
    )
    return ok(page)


@router.get("/{resume_id}", response_model=Envelope[ResumeOut], summary="Get a parsed resume")
async def get_resume(
    resume_id: str, session: SessionDep, container: ContainerDep, _: CurrentUser
) -> dict:
    return ok(resume_out(await ResumeService(session, container).get(resume_id)))


@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a resume",
    description="Uploader or admin only (403). Cascades to sections, embeddings and matches.",
)
async def delete_resume(
    resume_id: str, session: SessionDep, container: ContainerDep, user: CurrentUser
) -> Response:
    await ResumeService(session, container).delete(resume_id, user)
    return Response(status_code=204)
