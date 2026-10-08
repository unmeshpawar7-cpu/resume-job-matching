"""SQLAlchemy 2.0 ORM models.

Timestamps are naive UTC (portable ordering on SQLite and PostgreSQL). IDs are UUID
strings. Deleting a resume cascades to its sections and match results at the database
level (``ON DELETE CASCADE``) and in the ORM (``passive_deletes``).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from resume_matching.db.types import EmbeddingType, JSONType, new_id, utcnow

#: Fixed at schema-creation time; must equal EMBEDDING_DIM (pgvector columns are typed).
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "512"))


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="recruiter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    text: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONType)
    parser_version: Mapped[str] = mapped_column(String(20))
    taxonomy_version: Mapped[str] = mapped_column(String(20))
    embedding_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    sections: Mapped[list[ResumeSection]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ResumeSection.position",
    )


class ResumeSection(Base):
    __tablename__ = "resume_sections"
    __table_args__ = (UniqueConstraint("resume_id", "section_type", name="uq_section_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    section_type: Mapped[str] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType(EMBEDDING_DIM))

    resume: Mapped[Resume] = relationship(back_populates="sections")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    request: Mapped[dict[str, Any]] = mapped_column(JSONType)  # explicit skills / min years
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", "scoring_version", name="uq_match_version"),
        Index("ix_match_job_version_score", "job_id", "scoring_version", "overall_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    scoring_version: Mapped[str] = mapped_column(String(40))
    overall_score: Mapped[float] = mapped_column(Float, index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONType)
    explanation_source: Mapped[str] = mapped_column(String(30))
    prompt_version: Mapped[str] = mapped_column(String(60))
    llm_provider: Mapped[str] = mapped_column(String(30))
    llm_model: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    operation: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("match_results.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean)
    error_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
