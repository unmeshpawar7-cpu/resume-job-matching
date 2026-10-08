"""The hand-written Alembic migration must produce exactly the ORM schema."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from resume_matching.db.models import Base

ROOT = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "src/resume_matching/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migration_matches_models_and_downgrades(tmp_path):
    db = tmp_path / "migrated.db"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(f"sqlite:///{db}"))
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        migrated = {c["name"] for c in inspector.get_columns(name)}
        assert migrated == {c.name for c in table.columns}, name
    uniques = {u["name"] for u in inspector.get_unique_constraints("match_results")}
    assert "uq_match_version" in uniques
    fks = inspector.get_foreign_keys("resume_sections")
    assert fks[0]["options"].get("ondelete") == "CASCADE"

    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(f"sqlite:///{db}")).get_table_names()) <= {"alembic_version"}
