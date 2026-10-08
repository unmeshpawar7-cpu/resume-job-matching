"""Deterministic feature-hashing embeddings (offline default).

Features: lower-cased word unigrams and bigrams plus character 3- to 5-grams of each word,
hashed with BLAKE2b (stable across processes, unlike ``hash()``) into ``dim`` buckets with
a sign bit, log-scaled term frequency, L2-normalised.

This is a *lexical* representation: it captures shared vocabulary and morphology
("microservice" ~ "microservices"), not meaning. Good enough as an offline, reproducible
baseline; use ``EMBEDDING_PROVIDER=openai`` for semantic embeddings.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.]*[a-z0-9+#]|[a-z0-9]")
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is",
    "it", "of", "on", "or", "our", "the", "to", "we", "with", "you", "your", "will", "this",
    "that", "were", "was", "i", "my", "me",
})  # fmt: skip
VERSION = "v1"


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _features(text: str) -> dict[str, float]:
    tokens = tokenize(text)
    counts: dict[str, float] = {}

    def add(feature: str, weight: float) -> None:
        counts[feature] = counts.get(feature, 0.0) + weight

    for tok in tokens:
        add(f"w:{tok}", 1.0)
        padded = f"<{tok}>"
        for n in (3, 4, 5):
            for i in range(max(0, len(padded) - n + 1)):
                add(f"c{n}:{padded[i : i + n]}", 0.25)
    for a, b in itertools.pairwise(tokens):
        add(f"b:{a} {b}", 0.75)
    return counts


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % dim, (1.0 if (value >> 63) & 1 else -1.0)


class HashingEmbeddingProvider:
    name = "hashing"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.model_id = f"hashing-{VERSION}-{dim}"

    def embed_one(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float64)
        for feature, tf in _features(text).items():
            index, sign = _bucket(feature, self.dim)
            vec[index] += sign * (1.0 + math.log(tf)) if tf >= 1 else sign * tf
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return [round(float(x), 6) for x in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]
