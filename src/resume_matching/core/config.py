"""Application configuration loaded from environment variables (12-factor).

Two settings objects exist:

* :class:`Settings` - infrastructure, security, providers, limits.
* :class:`ScoringSettings` - every tunable number of the scoring formula. Kept separate
  because its fingerprint becomes part of ``scoring_version`` (changing a weight must not
  silently reuse results computed with the old weights).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TAXONOMY_PATH = PROJECT_ROOT / "data" / "skills_taxonomy.yaml"
_INSECURE_DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105

#: Version of the scoring *algorithm*. Bump when the code of a component changes.
SCORING_ALGORITHM_VERSION = "1.0.0"


class ScoringSettings(BaseSettings):
    """Weights, curves and caps of the scoring formula (see docs/scoring.md)."""

    model_config = SettingsConfigDict(env_prefix="SCORING_", env_file=".env", extra="ignore")

    weight_required_skills: float = Field(0.40, ge=0)
    weight_nice_to_have: float = Field(0.10, ge=0)
    weight_experience: float = Field(0.20, ge=0)
    weight_role: float = Field(0.10, ge=0)
    weight_semantic: float = Field(0.20, ge=0)

    #: Credit for a required skill satisfied only by a *related* skill (e.g. Flask for FastAPI).
    related_skill_credit: float = Field(0.5, ge=0, le=1)

    #: Experience curve: ratio r = candidate_years / min_years.
    experience_meets_score: float = Field(90.0, ge=0, le=100)
    experience_half_score: float = Field(40.0, ge=0, le=100)
    experience_overqualified_slope: float = Field(20.0, ge=0)

    #: Role alignment = title_weight * title similarity + (1 - title_weight) * seniority fit.
    role_title_weight: float = Field(0.7, ge=0, le=1)

    #: Semantic score = mix of max and mean section cosine, linearly rescaled from
    #: [floor, ceiling] to [0, 100]. Calibrated per embedding provider (lexical hashing
    #: vectors produce much lower raw cosines than neural embeddings).
    semantic_max_weight: float = Field(0.7, ge=0, le=1)
    semantic_floor_hashing: float = 0.05
    semantic_ceiling_hashing: float = 0.45
    semantic_floor_openai: float = 0.20
    semantic_ceiling_openai: float = 0.70

    #: Knock-out caps applied to the overall score.
    knockout_missing_critical_cap: float = Field(40.0, ge=0, le=100)
    knockout_experience_ratio: float = Field(0.5, ge=0, le=1)
    knockout_experience_cap: float = Field(60.0, ge=0, le=100)

    @model_validator(mode="after")
    def _weights_positive(self) -> ScoringSettings:
        if self.total_weight() <= 0:
            raise ValueError("At least one scoring weight must be > 0")
        return self

    def total_weight(self) -> float:
        return (
            self.weight_required_skills
            + self.weight_nice_to_have
            + self.weight_experience
            + self.weight_role
            + self.weight_semantic
        )

    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:8]

    def scoring_version(self) -> str:
        """Algorithm version + config fingerprint, e.g. ``1.0.0+3fa9c1d2`` (semver build)."""
        return f"{SCORING_ALGORITHM_VERSION}+{self.fingerprint()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "resume-job-matching"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "sqlite+aiosqlite:///./resume_matching.db"
    #: Create tables on startup (SQLite/dev convenience). Production uses Alembic.
    db_create_all: bool = True

    jwt_secret: SecretStr = SecretStr(_INSECURE_DEV_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "resume-job-matching"
    jwt_audience: str = "resume-job-matching-api"
    jwt_expires_minutes: int = Field(60, ge=1, le=24 * 60)
    bcrypt_rounds: int = Field(12, ge=4, le=16)
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None

    # --- AI providers -------------------------------------------------------------------
    llm_provider: Literal["offline", "openai", "anthropic"] = "offline"
    embedding_provider: Literal["hashing", "openai"] = "hashing"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    embedding_dim: int = Field(512, ge=64, le=4096)
    llm_timeout_seconds: float = Field(30.0, gt=0)
    llm_max_retries: int = Field(3, ge=1, le=6)
    llm_validation_retries: int = Field(2, ge=0, le=5)
    llm_max_output_tokens: int = Field(700, ge=100, le=4000)

    # --- Uploads ------------------------------------------------------------------------
    max_upload_bytes: int = Field(2 * 1024 * 1024, ge=1024)
    max_pdf_pages: int = Field(10, ge=1)
    max_docx_uncompressed_bytes: int = Field(20 * 1024 * 1024, ge=1024)

    # --- Behaviour ----------------------------------------------------------------------
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    redact_analysis_payloads: bool = True
    analyze_rate_limit_per_minute: float = Field(20.0, gt=0)
    analyze_rate_limit_burst: int = Field(10, ge=1)
    login_rate_limit_per_minute: float = Field(10.0, gt=0)
    login_rate_limit_burst: int = Field(5, ge=1)
    #: Above this many resumes, ranking first retrieves the N most semantically similar
    #: resumes via the vector store, then scores those deterministically.
    ranking_candidate_pool: int = Field(500, ge=1)

    @model_validator(mode="after")
    def _secure_in_production(self) -> Settings:
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.app_env == "production" and secret == _INSECURE_DEV_SECRET:
            raise ValueError("JWT_SECRET must be set explicitly in production")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_scoring_settings() -> ScoringSettings:
    return ScoringSettings()
