from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from resume_matching.ai.llm.base import LLMRequest, LLMResponse
from resume_matching.core.config import DEFAULT_TAXONOMY_PATH, ScoringSettings, Settings
from resume_matching.domain.taxonomy import SkillTaxonomy, cached_taxonomy
from resume_matching.main import create_app

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
TODAY = date(2026, 10, 8)
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password-123"


@pytest.fixture(scope="session")
def taxonomy() -> SkillTaxonomy:
    return cached_taxonomy(str(DEFAULT_TAXONOMY_PATH))


@pytest.fixture
def scoring() -> ScoringSettings:
    return ScoringSettings(_env_file=None)


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": "sqlite+aiosqlite:///:memory:",
        "jwt_secret": "test-secret-that-is-long-enough-0123456789",
        "bcrypt_rounds": 4,
        "log_json": True,
        "log_level": "WARNING",
        "analyze_rate_limit_burst": 100,
        "analyze_rate_limit_per_minute": 600,
        "login_rate_limit_burst": 100,
        "login_rate_limit_per_minute": 600,
        "max_upload_bytes": 200_000,
        "bootstrap_admin_email": ADMIN_EMAIL,
        "bootstrap_admin_password": ADMIN_PASSWORD,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class ScriptedLLM:
    """Test double at the provider interface: returns queued responses in order."""

    name = "openai"
    model = "scripted-model"

    def __init__(self, responses: list[str | Exception] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        item = self.responses.pop(0) if self.responses else json.dumps(_default_answer(request))
        if isinstance(item, Exception):
            raise item
        return LLMResponse(text=item, model=self.model, input_tokens=120, output_tokens=60)


def _default_answer(request: LLMRequest) -> dict[str, Any]:
    facts = request.facts
    skills = facts["requiredMatched"][:2]
    return {
        "summary": f"The candidate scored {facts['overallScore']}% for this role overall.",
        "strengths": [f"Has {s}" for s in skills],
        "gaps": [],
        "skills_mentioned": skills,
    }


AppFactory = Callable[..., AsyncIterator[AsyncClient]]


@pytest.fixture
def app_factory(scoring: ScoringSettings):
    """Build an app + client; usage: ``async with app_factory(llm=...) as client``."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _make(**kwargs: Any) -> AsyncIterator[AsyncClient]:
        llm = kwargs.pop("llm", None)
        settings = make_settings(**kwargs)
        app = create_app(settings, scoring, llm=llm, today=lambda: TODAY)
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                client.app = app  # type: ignore[attr-defined]
                yield client

    return _make


@pytest.fixture
async def client(app_factory) -> AsyncIterator[AsyncClient]:
    async with app_factory() as c:
        yield c


async def register_and_login(
    client: AsyncClient, email: str = "recruiter@example.com", password: str = "recruiter-pass-1"
) -> dict[str, str]:
    r = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409), r.text
    return await login(client, email, password)


async def login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await client.post("/api/auth/token", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['accessToken']}"}


@pytest.fixture
async def auth(client: AsyncClient) -> dict[str, str]:
    return await register_and_login(client)


@pytest.fixture
async def admin_auth(client: AsyncClient) -> dict[str, str]:
    return await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def sample_resume(name: str) -> tuple[str, bytes]:
    path = SAMPLES / "resumes" / name
    return path.name, path.read_bytes()


def sample_job(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / "jobs" / name).read_text(encoding="utf-8"))


async def upload(client: AsyncClient, headers: dict[str, str], name: str) -> dict[str, Any]:
    filename, data = sample_resume(name)
    r = await client.post("/api/resumes", files={"file": (filename, data)}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def create_job(client: AsyncClient, headers: dict[str, str], name: str) -> dict[str, Any]:
    r = await client.post("/api/jobs", json=sample_job(name), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]
