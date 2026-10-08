from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from resume_matching.api.deps import ContainerDep, OptionalUser, SessionDep
from resume_matching.schemas.auth import RegisterRequest, TokenRequest, TokenResponse, UserOut
from resume_matching.schemas.common import Envelope, ok
from resume_matching.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[UserOut],
    summary="Register a user",
    description="Open registration creates a `recruiter`. Creating an `admin` requires an "
    "admin bearer token (403 otherwise). Duplicate e-mail returns 409.",
)
async def register(
    body: RegisterRequest, session: SessionDep, container: ContainerDep, actor: OptionalUser
) -> JSONResponse:
    user = await AuthService(session, container.settings).register(
        body.email, body.password, body.role, actor
    )
    out = UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)
    return JSONResponse(ok(out), status_code=201)


@router.post(
    "/token",
    response_model=Envelope[TokenResponse],
    summary="Obtain a JWT access token",
    description="Rate limited per client IP and e-mail (429 with Retry-After).",
)
async def token(
    body: TokenRequest, request: Request, session: SessionDep, container: ContainerDep
) -> dict:
    client = request.client.host if request.client else "unknown"
    container.login_limiter.check(f"{client}:{body.email.strip().lower()}")
    access, expires_in, user = await AuthService(session, container.settings).login(
        body.email, body.password
    )
    return ok(TokenResponse(access_token=access, expires_in=expires_in, role=user.role))
