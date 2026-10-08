"""In-process token-bucket rate limiter.

One bucket per key (user id or client IP). Suitable for a single API instance; behind
several replicas use a shared store (Redis) instead - documented as a future enhancement.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from resume_matching.core.errors import RateLimitedError


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    def __init__(
        self,
        rate_per_minute: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.rate_per_second = rate_per_minute / 60.0
        self.burst = burst
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def _evict_if_needed(self) -> None:
        if len(self._buckets) <= self._max_keys:
            return
        oldest = sorted(self._buckets.items(), key=lambda kv: kv[1].updated)
        for key, _ in oldest[: len(oldest) // 2]:
            del self._buckets[key]

    def try_acquire(self, key: str) -> tuple[bool, float]:
        """Consume one token. Returns ``(allowed, retry_after_seconds)``."""
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(self.burst), updated=now)
                self._buckets[key] = bucket
                self._evict_if_needed()
            elapsed = max(0.0, now - bucket.updated)
            bucket.tokens = min(float(self.burst), bucket.tokens + elapsed * self.rate_per_second)
            bucket.updated = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            return False, (1.0 - bucket.tokens) / self.rate_per_second

    def check(self, key: str) -> None:
        allowed, retry_after = self.try_acquire(key)
        if not allowed:
            raise RateLimitedError(retry_after)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
