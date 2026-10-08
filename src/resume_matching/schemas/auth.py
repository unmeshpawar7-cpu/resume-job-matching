from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from resume_matching.domain.base import DomainModel

_EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$"


class RegisterRequest(DomainModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=320, examples=["recruiter@example.com"])
    password: str = Field(min_length=10, max_length=72, examples=["correct-horse-battery"])
    role: Literal["recruiter", "admin"] = Field(
        "recruiter", description="Creating an admin requires an admin bearer token."
    )

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class TokenRequest(DomainModel):
    email: str = Field(max_length=320, examples=["recruiter@example.com"])
    password: str = Field(max_length=200, examples=["correct-horse-battery"])


class TokenResponse(DomainModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    role: str


class UserOut(DomainModel):
    id: str
    email: str
    role: str
    created_at: datetime
