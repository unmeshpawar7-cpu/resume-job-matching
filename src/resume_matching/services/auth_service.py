from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from resume_matching.core.config import Settings
from resume_matching.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from resume_matching.core.security import (
    Role,
    create_access_token,
    hash_password,
    verify_password,
)
from resume_matching.db.models import User
from resume_matching.repositories.users import UserRepository

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _dummy_hash(rounds: int) -> str:
    """Verified against when the e-mail is unknown, so response time does not reveal
    whether an account exists."""
    return hash_password("not-a-real-password", rounds)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)

    async def register(self, email: str, password: str, role: Role, actor: User | None) -> User:
        if role == "admin" and (actor is None or actor.role != "admin"):
            raise ForbiddenError("Only an admin can create admin accounts")
        if await self.users.get_by_email(email):
            raise ConflictError("An account with this email already exists")
        user = await self.users.add(
            User(
                email=email.lower(),
                password_hash=hash_password(password, self.settings.bcrypt_rounds),
                role=role,
            )
        )
        await self.session.commit()
        logger.info("user_registered", extra={"user_id": user.id, "role": role})
        return user

    async def login(self, email: str, password: str) -> tuple[str, int, User]:
        user = await self.users.get_by_email(email.strip().lower())
        valid = verify_password(
            password, user.password_hash if user else _dummy_hash(self.settings.bcrypt_rounds)
        )
        if user is None or not valid or not user.is_active:
            raise UnauthorizedError("Invalid email or password")
        token, expires_in = create_access_token(user.id, user.role, self.settings)  # type: ignore[arg-type]
        return token, expires_in, user

    async def ensure_admin(self, email: str, password: str) -> None:
        if await self.users.get_by_email(email):
            return
        await self.users.add(
            User(
                email=email.lower(),
                password_hash=hash_password(password, self.settings.bcrypt_rounds),
                role="admin",
            )
        )
        await self.session.commit()
        logger.info("bootstrap_admin_created")
