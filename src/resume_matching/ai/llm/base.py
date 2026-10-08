"""LLM provider protocol and shared helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    user: str
    #: The structured facts the prompt was rendered from. Remote providers ignore it (they
    #: read the prompt); the offline provider renders its template from it directly.
    facts: dict[str, Any] = field(default_factory=dict)
    max_output_tokens: int = 700


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class LLMProvider(Protocol):
    name: str  # "offline" | "openai" | "anthropic"
    model: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in ``text`` (tolerates code fences and preambles)."""
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("Response does not contain a JSON object") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("Top-level JSON value must be an object")
    return value


def is_transient(exc: BaseException) -> bool:
    """Retry on timeouts, connection errors, 429 and 5xx (by SDK class name, so the
    optional SDKs need not be importable for this check)."""
    return type(exc).__name__ in {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
        "OverloadedError",
        "ServiceUnavailableError",
        "TimeoutError",
    }
