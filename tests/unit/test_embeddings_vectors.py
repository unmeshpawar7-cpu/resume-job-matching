from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from resume_matching.ai.embeddings import build_embedding_provider
from resume_matching.ai.embeddings.hashing import HashingEmbeddingProvider, tokenize
from resume_matching.ai.embeddings.openai import OpenAIEmbeddingProvider
from resume_matching.ai.usage import usage_scope
from resume_matching.core.errors import ProviderError
from resume_matching.domain.scoring.components import cosine
from resume_matching.repositories.vector_store import InMemoryVectorStore
from tests.conftest import make_settings


async def test_hashing_embeddings_are_deterministic_and_normalised():
    emb = HashingEmbeddingProvider(128)
    a, b = await emb.embed(["Python FastAPI microservices", "Python FastAPI microservices"])
    assert a == b
    assert len(a) == 128
    assert np.linalg.norm(a) == pytest.approx(1.0, abs=1e-5)
    assert emb.model_id == "hashing-v1-128"
    assert emb.embed_one("") == [0.0] * 128


def test_hashing_similarity_reflects_vocabulary_overlap():
    emb = HashingEmbeddingProvider(512)
    jd = emb.embed_one("Backend engineer: Python, FastAPI, PostgreSQL, Docker microservices")
    close = emb.embed_one("Built Python FastAPI microservice on PostgreSQL with Docker")
    far = emb.embed_one("Pastry chef experienced with laminated doughs and sourdough")
    assert cosine(jd, close) > cosine(jd, far) + 0.2


def test_tokenize_keeps_tech_tokens():
    assert tokenize("C# and .NET with Node.js") == ["c#", "net", "node.js"]


async def test_openai_embedding_provider_with_fake_client():
    async def create(**kwargs):
        assert kwargs["dimensions"] == 4
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3, 0.4]) for _ in kwargs["input"]],
            usage=SimpleNamespace(prompt_tokens=9),
        )

    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    emb = OpenAIEmbeddingProvider(
        api_key=None, model="text-embedding-3-small", dim=4, timeout=5, client=client
    )
    with usage_scope() as records:
        vectors = await emb.embed(["a", "b"])
    assert vectors == [[0.1, 0.2, 0.3, 0.4]] * 2
    assert records[0].operation == "embedding" and records[0].input_tokens == 9
    assert await emb.embed([]) == []

    async def failing(**kwargs):
        raise RuntimeError("nope")

    broken = OpenAIEmbeddingProvider(
        api_key=None, model="m", dim=4, timeout=5,
        client=SimpleNamespace(embeddings=SimpleNamespace(create=failing)),
    )  # fmt: skip
    with usage_scope() as records, pytest.raises(ProviderError):
        await broken.embed(["x"])
    assert records[0].success is False


def test_embedding_factory():
    assert build_embedding_provider(make_settings()).name == "hashing"
    with pytest.raises(ProviderError):
        build_embedding_provider(make_settings(embedding_provider="openai"))


async def test_in_memory_vector_store_search_upsert_delete():
    store = InMemoryVectorStore()
    assert await store.search(None, [1, 0, 0], 5) == []
    store.load([("r1", "skills", [1, 0, 0]), ("r1", "experience", [0, 1, 0])])
    await store.upsert(None, "r2", {"skills": [0.9, 0.1, 0], "summary": [0, 0, 1]})
    hits = await store.search(None, [1, 0, 0], 5)
    assert [h[0] for h in hits] == ["r1", "r2"]
    assert hits[0][1] == pytest.approx(1.0)
    assert len(await store.search(None, [1, 0, 0], 1)) == 1
    await store.upsert(None, "r2", {"skills": [0, 0, 1]})
    assert len(store) == 3
    await store.delete(None, "r1")
    assert [h[0] for h in await store.search(None, [1, 0, 0], 5)] == ["r2"]
