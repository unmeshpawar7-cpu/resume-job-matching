"""FastAPI dependencies: container, DB session, authentication, pagination."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.core.errors import ForbiddenError, UnauthorizedError
from resume_matching.core.security import decode_access_token
from resume_matching.db.models import User
from resume_matching.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from resume_matching.services.container import AppContainer

bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /api/auth/token")


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def get_session(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    async with container.sessionmaker() as session:
        yield session


ContainerDep = Annotated[AppContainer, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _user_from_token(
    credentials: HTTPAuthorizationCredentials | None,
    container: AppContainer,
    session: AsyncSession,
) -> User | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    claims = decode_access_token(credentials.credentials, container.settings)
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User no longer exists or is inactive")
    return user


async def get_optional_user(
    container: ContainerDep,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    return await _user_from_token(credentials, container, session)


async def get_current_user(
    container: ContainerDep,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    user = await _user_from_token(credentials, container, session)
    if user is None:
        raise UnauthorizedError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(*roles: str) -> Callable[[User], Awaitable[User]]:
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError()
        return user

    return _check


@dataclass(frozen=True, slots=True)
class PageParams:
    page: int
    page_size: int


def pagination(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[
        int | None, Query(alias="pageSize", ge=1, description="Items per page (max 100)")
    ] = None,
    page_size_snake: Annotated[
        int | None, Query(alias="page_size", ge=1, include_in_schema=False)
    ] = None,
) -> PageParams:
    size = page_size or page_size_snake or DEFAULT_PAGE_SIZE
    return PageParams(page=page, page_size=min(size, MAX_PAGE_SIZE))


PageDep = Annotated[PageParams, Depends(pagination)]
