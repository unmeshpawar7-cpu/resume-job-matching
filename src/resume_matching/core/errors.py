"""Application error hierarchy. Every error maps to one HTTP status and the error envelope."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    message: str


class AppError(Exception):
    status_code: int = 500
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.errors = errors or []
        self.headers = headers or {}
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    default_message = "Bad request"


class UnauthorizedError(AppError):
    status_code = 401
    default_message = "Not authenticated"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(AppError):
    status_code = 403
    default_message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = 404
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    default_message = "Resource already exists"


class PayloadTooLargeError(AppError):
    status_code = 413
    default_message = "Payload too large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    default_message = "Unsupported media type"


class UnprocessableError(AppError):
    status_code = 422
    default_message = "Validation failed"


class RateLimitedError(AppError):
    status_code = 429
    default_message = "Too many requests"

    def __init__(self, retry_after_seconds: float) -> None:
        seconds = max(1, int(retry_after_seconds + 0.999))
        super().__init__(
            f"Rate limit exceeded; retry in {seconds}s",
            headers={"Retry-After": str(seconds)},
        )


class ProviderError(AppError):
    """An upstream AI provider failed after retries."""

    status_code = 502
    default_message = "Upstream AI provider failed"
