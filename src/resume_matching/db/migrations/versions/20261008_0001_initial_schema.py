"""Initial schema: users, resumes, resume_sections (+pgvector), jobs, match_results, ai_usage.

Hand-written to match ``resume_matching.db.models``. On PostgreSQL it enables the
``vector`` extension, types embedding columns as ``vector(EMBEDDING_DIM)`` and creates an
HNSW index (cosine ops) on section embeddings. On other dialects embeddings are JSON.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-08
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "512"))


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _json() -> sa.types.TypeEngine:
    return postgresql.JSONB() if _is_pg() else sa.JSON()


def _embedding() -> sa.types.TypeEngine:
    return Vector(EMBEDDING_DIM) if _is_pg() else sa.JSON()


def upgrade() -> None:
    if _is_pg():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer()),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("profile", _json(), nullable=False),
        sa.Column("parser_version", sa.String(20), nullable=False),
        sa.Column("taxonomy_version", sa.String(20), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("checksum", name="uq_resumes_checksum"),
    )
    op.create_index("ix_resumes_owner_id", "resumes", ["owner_id"])
    op.create_index("ix_resumes_created_at", "resumes", ["created_at"])

    op.create_table(
        "resume_sections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_type", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", _embedding()),
        sa.UniqueConstraint("resume_id", "section_type", name="uq_section_type"),
    )
    op.create_index("ix_resume_sections_resume_id", "resume_sections", ["resume_id"])
    if _is_pg():
        op.execute(
            "CREATE INDEX ix_resume_sections_embedding_hnsw ON resume_sections "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
        )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("request", _json(), nullable=False),
        sa.Column("analysis", _json(), nullable=False),
        sa.Column("embedding", _embedding()),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "match_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scoring_version", sa.String(40), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("result", _json(), nullable=False),
        sa.Column("explanation", _json(), nullable=False),
        sa.Column("explanation_source", sa.String(30), nullable=False),
        sa.Column("prompt_version", sa.String(60), nullable=False),
        sa.Column("llm_provider", sa.String(30), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("resume_id", "job_id", "scoring_version", name="uq_match_version"),
    )
    op.create_index("ix_match_results_resume_id", "match_results", ["resume_id"])
    op.create_index("ix_match_results_overall_score", "match_results", ["overall_score"])
    op.create_index(
        "ix_match_job_version_score",
        "match_results",
        ["job_id", "scoring_version", "overall_score"],
    )

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(60)),
        sa.Column(
            "match_id", sa.String(36), sa.ForeignKey("match_results.id", ondelete="SET NULL")
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float()),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(100)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_usage_operation", "ai_usage", ["operation"])
    op.create_index("ix_ai_usage_match_id", "ai_usage", ["match_id"])
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("match_results")
    op.drop_table("jobs")
    op.drop_table("resume_sections")
    op.drop_table("resumes")
    op.drop_table("users")
