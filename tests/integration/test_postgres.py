"""PostgreSQL + pgvector integration tests. Skipped unless TEST_DATABASE_URL is set, e.g.

TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/resume_matching_test
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from resume_matching.core.config import ScoringSettings
from resume_matching.db.session import create_engine
from resume_matching.main import create_app
from resume_matching.repositories.vector_store import PgVectorStore
from tests.conftest import TODAY, create_job, make_settings, register_and_login, upload

pytestmark = pytest.mark.postgres
URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]

if not URL:
    pytest.skip("TEST_DATABASE_URL not set", allow_module_level=True)


def _alembic(direction: str) -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "src/resume_matching/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", URL)
    getattr(command, direction)(cfg, "head" if direction == "upgrade" else "base")


@pytest.fixture(scope="module", autouse=True)
def migrated_db():
    _alembic("downgrade")
    _alembic("upgrade")
    yield
    _alembic("downgrade")


async def test_migration_creates_pgvector_schema():
    engine = create_engine(URL)
    async with engine.connect() as conn:
        ext = await conn.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        col = await conn.scalar(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'resume_sections'::regclass AND attname = 'embedding'"
            )
        )
        index = await conn.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_resume_sections_embedding_hnsw'"
            )
        )
    await engine.dispose()
    assert ext == "vector"
    assert col == "vector(512)"
    assert "hnsw" in index and "vector_cosine_ops" in index


async def test_full_flow_on_postgres_with_pgvector_preselection():
    settings = make_settings(database_url=URL, db_create_all=False, ranking_candidate_pool=2)
    app = create_app(settings, ScoringSettings(_env_file=None), today=lambda: TODAY)
    assert isinstance(app.state.container.vector_store, PgVectorStore)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pg") as client:
            headers = await register_and_login(client, "pg@example.com", "pg-password-123")
            ids = {}
            for name in (
                "daniel_okafor_ai_backend.txt",
                "rohan_deshpande_dotnet_backend.pdf",
                "sofia_alvarez_data_engineer.txt",
            ):
                ids[name] = (await upload(client, headers, name))["id"]
            job = await create_job(client, headers, "dotnet_backend_developer.json")
            analyzed = await client.post(
                "/api/matching/analyze",
                json={"resumeId": ids["rohan_deshpande_dotnet_backend.pdf"], "jobId": job["id"]},
                headers=headers,
            )
            assert analyzed.status_code == 201
            ranking = (
                await client.get(f"/api/candidates/ranking?job_id={job['id']}", headers=headers)
            ).json()["data"]
            assert ranking["candidatesConsidered"] == 2
            assert ranking["items"][0]["resumeId"] == ids["rohan_deshpande_dotnet_backend.pdf"]
            deleted = await client.delete(
                f"/api/resumes/{ids['rohan_deshpande_dotnet_backend.pdf']}", headers=headers
            )
            assert deleted.status_code == 204
            gone = await client.get(
                f"/api/matching/{analyzed.json()['data']['id']}", headers=headers
            )
            assert gone.status_code == 404
