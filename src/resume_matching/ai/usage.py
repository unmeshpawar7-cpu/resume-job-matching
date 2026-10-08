"""AI usage accounting: latency, token estimates and estimated cost per call.

Records never contain prompt or resume content - only metadata (provider, model, prompt
version, latency, token counts, success, error type). Providers call :func:`record_usage`;
the service layer opens a :func:`usage_scope` per operation and persists the collected
records to the ``ai_usage`` table. Every record is also emitted as a structured log line.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass

logger = logging.getLogger("resume_matching.ai.usage")

#: Approximate USD prices per 1M tokens (input, output). Estimates only - check the
#: provider's price list; unknown models are recorded with cost ``None``.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_tokens(text: str) -> int:
    """Rough heuristic (~4 characters per token) used when the provider reports none."""
    return max(1, (len(text) + 3) // 4) if text else 0


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 6)


@dataclass(slots=True)
class UsageRecord:
    operation: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    success: bool
    prompt_version: str | None = None
    error_type: str | None = None
    attempt: int = 1
    estimated_cost_usd: float | None = None


_current: ContextVar[list[UsageRecord] | None] = ContextVar("ai_usage_records", default=None)


def record_usage(**kwargs: object) -> UsageRecord:
    rec = UsageRecord(**kwargs)  # type: ignore[arg-type]
    rec.latency_ms = round(rec.latency_ms, 2)
    if rec.estimated_cost_usd is None:
        rec.estimated_cost_usd = estimate_cost(rec.model, rec.input_tokens, rec.output_tokens)
    bucket = _current.get()
    if bucket is not None:
        bucket.append(rec)
    logger.info("ai_call", extra={"ai": asdict(rec)})
    return rec


@contextmanager
def usage_scope() -> Iterator[list[UsageRecord]]:
    """Collect every :class:`UsageRecord` emitted inside the ``with`` block."""
    records: list[UsageRecord] = []
    token = _current.set(records)
    try:
        yield records
    finally:
        _current.reset(token)
