# syntax=docker/dockerfile:1.7
# ---- build stage: build wheels (incl. optional provider SDKs) -------------------------
FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels ".[openai,anthropic]"

# ---- runtime stage --------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TAXONOMY_PATH=/app/data/skills_taxonomy.yaml
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels
COPY --chown=app:app data ./data
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app src/resume_matching/db/migrations ./src/resume_matching/db/migrations
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)" || exit 1
CMD ["uvicorn", "resume_matching.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
