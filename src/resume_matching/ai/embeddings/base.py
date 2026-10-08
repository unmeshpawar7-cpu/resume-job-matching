"""Embedding provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    #: "hashing" or "openai" - selects the semantic-score calibration.
    name: str
    #: Stable identifier stored with every vector, e.g. ``hashing-v1-512``.
    model_id: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
