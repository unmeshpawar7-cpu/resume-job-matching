"""Password hashing (bcrypt) and JWT issuing/verification (PyJWT)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from resume_matching.core.config import Settings
from resume_matching.core.errors import UnauthorizedError

Role = Literal["recruiter", "admin"]
ROLES: tuple[Role, ...] = ("recruiter", "admin")
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str, rounds: int = 12) -> str:
    data = password.encode("utf-8")
    if len(data) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long (max 72 bytes)")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode("utf-8")
    if len(data) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(data, password_hash.encode("ascii"))
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: str
    role: Role
    expires_at: datetime


def create_access_token(user_id: str, role: Role, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = settings.jwt_expires_minutes * 60
    payload = {
        "sub": user_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "role", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token") from exc
    role = payload.get("role")
    if role not in ROLES:
        raise UnauthorizedError("Invalid token role")
    return TokenClaims(
        user_id=str(payload["sub"]),
        role=role,
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )
