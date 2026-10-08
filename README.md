# Resume-Job Matching API

Explainable resume ↔ job-description matching: a deterministic + semantic score with a full evidence breakdown, and an LLM-written narrative that **never changes the number**.

[![CI](https://github.com/unmeshpawar7-cpu/resume-job-matching/actions/workflows/ci.yml/badge.svg)](https://github.com/unmeshpawar7-cpu/resume-job-matching/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)
![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-336791.svg)

## Problem

Resume screening tools tend to be one of two things. Keyword filters are brittle: they
can't tell `Java` from `JavaScript`, and they reject "Flask" when the job asks for
"FastAPI". "Ask the LLM for a match %" tools give numbers that can't be reproduced or
audited, that change with prompt wording, and that may pick up names, ages or addresses
from the raw text. Recruiters need a score they can defend and explain to a candidate.

## Solution

* **Deterministic first.** A versioned scoring engine combines five evidence-backed
  components: required-skill coverage, nice-to-have coverage, experience fit, role/title
  alignment and calibrated embedding similarity. It also applies knock-out caps for missing
  must-haves.
* **The LLM only narrates.** It receives the computed facts and never sees the resume text.
  Its JSON output is validated with Pydantic and checked for grounding: it must not
  mention skills outside the facts or state a different percentage. If it fails, it is
  retried and then replaced by a deterministic template.
* **Reproducible.** Results are idempotent per `(resume, job, scoring_version)`. The
  scoring version fingerprints the weights, the embedding model and the taxonomy version.

## Architecture

```mermaid
flowchart LR
    U[Recruiter / ATS] -->|JWT| API[FastAPI routers<br/>envelope, rate limits]
    API --> SVC[Services]
    SVC --> PARSE[Parser<br/>PDF/DOCX/TXT + sections]
    SVC --> DOM[Domain<br/>taxonomy, experience,<br/>JD analysis, scoring]
    SVC --> EMB[EmbeddingProvider<br/>hashing / OpenAI]
    SVC --> EXPL[ExplanationGenerator]
    EXPL --> LLM[LLMProvider<br/>offline / OpenAI / Anthropic]
    SVC --> REPO[Repositories + VectorStore]
    REPO --> PG[(PostgreSQL + pgvector)]
```

More diagrams (component view, analyze sequence, ranking) are in
[docs/architecture.md](docs/architecture.md).

## Key Features

* Upload `.pdf`, `.docx` or `.txt` resumes. Extension and magic bytes must agree (415).
  The size limit is enforced while streaming (413). There are PDF page limits and a DOCX
  zip-bomb guard.
* Section detection. The header and personal sections are excluded from scoring.
* Skill extraction against a curated taxonomy of ~190 skills with aliases, categories and
  related skills. Matching is boundary-safe: `Java` ≠ `JavaScript`, and `C#`, `.NET`,
  `Node.js`, `k8s` and case-sensitive `Go` are handled.
* Experience extraction from date ranges such as `Jan 2021 – Present`, `03/2019 – 05/2022`
  and `2019-2022`. Overlaps are merged so concurrent jobs are not double counted. Per-skill
  recency and years are tracked.
* Title and seniority detection, plus role families (backend, ml_ai, data, ...).
* JD analysis splits critical, required and nice-to-have skills. It uses cue phrases
  ("must have", "a plus", "preferred", block headings) or explicit lists, and also finds
  the minimum years and seniority.
* Explainable scoring returns weights, effective weights, contributions, matched/missing
  skills with match type (`exact`, `alias`, `related`, `literal`), knock-outs, raw vs
  capped score, deterministic recommended improvements and interview-prep topics.
* LLM explanation with versioned prompts, structured output, grounding checks, bounded
  retries, template fallback and per-call usage/cost accounting.
* Candidate ranking batch-computes missing matches without LLM calls and uses
  deterministic tie-breaks. Above a configurable pool size it pre-selects candidates with
  pgvector.
* Security: JWT auth (PyJWT + bcrypt), `recruiter`/`admin` roles, PII redaction in logs
  and in stored text, per-user analyze rate limit, login throttling, and resume deletion
  that cascades to sections, vectors and matches.

## Technology Stack

| Area | Choice |
|---|---|
| API | FastAPI, Pydantic v2, pydantic-settings, python-multipart |
| Persistence | SQLAlchemy 2.0 async (asyncpg / aiosqlite), Alembic, PostgreSQL 16 + pgvector (HNSW) |
| Parsing | pypdf, python-docx, PyYAML |
| AI | OpenAI and Anthropic SDKs (optional extras), tenacity, numpy |
| Security | PyJWT, bcrypt |
| Quality | pytest, pytest-asyncio, httpx AsyncClient, pytest-cov, ruff |
| Ops | Docker (multi-stage, non-root), docker-compose, GitHub Actions |

## Project Structure

```
src/resume_matching/
  api/            routers (auth, resumes, jobs, matching, candidates, health), deps, errors, middleware
  services/       AuthService, ResumeService, JobService, MatchingService, AppContainer
  domain/         taxonomy, sections, experience, roles, profile, job_analysis, ranking
    scoring/      components, engine, advice (recommendations + interview topics), models
  ai/             embeddings/ (hashing, openai), llm/ (offline, openai, anthropic),
                  prompts/match_explanation/v1.md, contracts, explanation, narrative, usage
  parsing/        file validation + text extraction
  repositories/   users, resumes, jobs, matches/ai_usage, vector_store (pgvector / in-memory)
  db/             models, types (JSONB / vector), session, migrations/ (Alembic)
  core/           config, errors, logging, redaction, security, rate_limit
  main.py         app factory
data/skills_taxonomy.yaml   curated, versioned taxonomy
samples/        resumes (.txt, .docx, .pdf) and job descriptions (JSON payloads)
scripts/        generate_sample_documents.py, capture_api_examples.py
tests/          unit/, api/, integration/ (migrations, @pytest.mark.postgres)
docs/           architecture.md, scoring.md, api-examples.md, adr/
docker/Dockerfile, docker-compose.yml, .github/workflows/ci.yml
```

## API Endpoints

All `/api` responses use the envelope `{success, data, message}`. Errors use
`{success:false, message, errors[{field,message}], traceId}`. List endpoints accept
`page` and `pageSize` (or `page_size`), with `pageSize` capped at 100.

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | public (admin token to create `admin`) | Register a user. 201, 409 on duplicate e-mail, 403 for admin without an admin token |
| POST | `/api/auth/token` | public | Get a JWT. 401 on bad credentials, 429 when throttled |
| POST | `/api/resumes` | recruiter/admin | Multipart upload, returns the parsed profile. 201 + Location, 409/413/415/422 |
| GET | `/api/resumes` | recruiter/admin | Paginated resume summaries |
| GET | `/api/resumes/{id}` | recruiter/admin | Parsed profile |
| DELETE | `/api/resumes/{id}` | uploader or admin | 204. Cascades to sections, embeddings and matches; 403 for others |
| POST | `/api/jobs` | recruiter/admin | Create and analyse a JD. 201 + Location |
| GET | `/api/jobs` | recruiter/admin | Paginated job summaries |
| GET | `/api/jobs/{id}` | recruiter/admin | Job with analysis |
| POST | `/api/matching/analyze` | recruiter/admin | `{resumeId, jobId, force?}`. 201 for a new result, 200 for an existing one (or forced recompute). Rate limited (429) |
| GET | `/api/matching/{id}` | recruiter/admin | Stored match result |
| GET | `/api/candidates/ranking` | recruiter/admin | `job_id`, `page`, `pageSize`, `min_score`: ranked, paginated candidates with top reasons |
| GET | `/health/live`, `/health/ready` | public | Liveness; readiness (DB + taxonomy, 503 when not ready) |

OpenAPI/Swagger UI is served at `/docs`.

## Database Design

```mermaid
erDiagram
    users {
        string id PK
        string email UK
        string password_hash
        string role "recruiter | admin"
        bool is_active
        datetime created_at
    }
    resumes {
        string id PK
        string owner_id FK
        string filename
        string file_type
        string checksum UK "sha256 of the upload"
        text text "PII-redacted by default"
        json profile "skills, positions, titles"
        string taxonomy_version
        string embedding_model
        datetime created_at
    }
    resume_sections {
        string id PK
        string resume_id FK "ON DELETE CASCADE"
        string section_type
        text text
        vector embedding "vector(512), HNSW cosine"
    }
    jobs {
        string id PK
        string owner_id FK
        string title
        text description
        json request
        json analysis
        vector embedding
        string embedding_model
    }
    match_results {
        string id PK
        string resume_id FK "ON DELETE CASCADE"
        string job_id FK "ON DELETE CASCADE"
        string scoring_version "UK with resume_id, job_id"
        float overall_score "indexed (job, version, score)"
        json result
        json explanation
        string explanation_source
        string prompt_version
        string llm_provider
    }
    ai_usage {
        string id PK
        string match_id FK
        string operation
        string provider
        string model
        string prompt_version
        float latency_ms
        int input_tokens
        int output_tokens
        float estimated_cost_usd
        bool success
    }
    users ||--o{ resumes : uploads
    users ||--o{ jobs : creates
    resumes ||--o{ resume_sections : has
    resumes ||--o{ match_results : "scored in"
    jobs ||--o{ match_results : "scored in"
    match_results ||--o{ ai_usage : "explained by"
```

The Alembic migration is hand-written: it enables the `vector` extension and creates the
HNSW index. A test checks it against the ORM models, and it was run against a real
pgvector database (see Testing).

## AI Architecture

```mermaid
flowchart LR
    subgraph Deterministic
        P[Profile + JD analysis] --> SC[Scoring engine]
        E1[Section + JD embeddings] --> SC
        SC --> F[ExplanationFacts<br/>scores, skill names,<br/>recommendations, allowedSkills]
    end
    F --> PR[Prompt match_explanation/v1]
    PR --> L[LLMProvider]
    L --> V{Pydantic schema<br/>+ grounding}
    V -- ok --> X[explanation source=llm]
    V -- violations --> RT[Retry with errors<br/>max LLM_VALIDATION_RETRIES]
    RT --> L
    RT -- exhausted / provider error --> T[Template<br/>source=template_fallback]
```

* **Providers.** `LLM_PROVIDER=offline|openai|anthropic` (default `offline`) and
  `EMBEDDING_PROVIDER=hashing|openai` (default `hashing`). The SDKs are optional extras
  (`pip install .[openai,anthropic]`) and are imported lazily. Calls use tenacity retries
  for transient errors (timeouts, 429, 5xx), explicit timeouts and `temperature=0`.
* **Offline mode.** `OfflineTemplateProvider` is **not an LLM**. It renders the
  explanation from the facts with fixed templates and goes through the same validation
  path. The `hashing` embedder is lexical feature hashing (word uni/bigrams + char
  n-grams, BLAKE2b, L2-normalised). It measures vocabulary overlap, not meaning. Semantic
  calibration is set per provider.
* **Prompt versioning.** Prompts live in `ai/prompts/<name>/<version>.md`. The version id
  (`match_explanation/v1`) is stored with every match and every `ai_usage` row.
* **Structured output.** The model must return `{summary, strengths[], gaps[],
  skills_mentioned[]}`, which is validated with Pydantic. Validation errors are fed back to
  the model on retry.
* **Hallucination mitigation.** The model only sees facts, with no resume text. The output
  is rejected if `skills_mentioned` or the prose names a taxonomy skill outside
  `allowedSkills`, or if any `NN%` or `NN/100` figure differs from a computed score. The
  number shown to users always comes from the engine.
* **Cost and tokens.** Each call records provider, model, prompt version, latency,
  input/output tokens (provider-reported or estimated at ~4 chars/token), estimated USD
  cost (from a small price table, an estimate only), success, error type and attempt. No
  prompt or resume content is logged or stored. Batch ranking makes **no** LLM calls;
  narratives are attached lazily when a match is opened via `analyze`.

## Security

* JWT (HS256, issuer/audience/expiry required). Passwords are hashed with bcrypt.
  `JWT_SECRET` must be at least 32 characters and must be set explicitly in production.
* Roles: open registration creates `recruiter`; only an admin can create admins. Resume
  deletion is limited to the uploader or an admin (403 otherwise). An optional bootstrap
  admin can be created from env.
* Uploads: allow-listed extensions plus magic-byte checks (415), streamed size limit
  (413), PDF page cap, DOCX uncompressed-size cap, encrypted PDFs rejected. Nothing is
  rendered or executed.
* Privacy: e-mails, phone numbers and profile URLs are redacted from all log records and
  (by default, `REDACT_ANALYSIS_PAYLOADS=true`) from stored resume text. Embedding inputs
  are redacted and have years masked. Deleting a resume cascades to its sections, vectors
  and match results.
* Rate limits: an in-process token bucket per user on `analyze` and per IP+e-mail on login
  (429 with `Retry-After`). With several replicas this needs a shared store.
* **Fairness note.** The scorer ignores names, gender, age, photos and addresses, and the
  code does not use them. The header and personal sections (interests, languages,
  references, volunteering) are excluded from skills, embeddings and scoring by
  construction. Years are masked before embedding (graduation year is an age proxy).
  Over-qualification is never penalised. A unit test asserts that changing name, e-mail,
  phone and address, and adding a personal section, leaves every component score
  unchanged. This removes direct use of these attributes. It does not prove the absence of
  every proxy bias (for example, wording differences). Human review remains part of the
  process.

## Testing

```bash
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov                               # unit + API (SQLite) + migration test
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/resume_matching_test \
  pytest -m postgres                       # pgvector integration tests
```

Measured in this repository (Python 3.13):

* **130 passed, 1 skipped (postgres module) on SQLite, with 97% line+branch coverage.**
* With `TEST_DATABASE_URL` pointing at a local PostgreSQL 16 + pgvector 0.6.0 cluster:
  **132 passed, 97% coverage.**

What is covered:

* **Unit.** Section detection, PDF/DOCX/TXT extraction and rejection, taxonomy edge cases
  (`Java`/`JavaScript`, `C#`, `.NET`, `Node.js`, case-sensitive `Go`/`SOLID`),
  date-range parsing and overlap merging, JD cue classification, every scoring component,
  weight redistribution, both knock-outs, config-driven weights and scoring version,
  determinism, fairness invariance, ranking order and ties, grounding checks, retry and
  fallback paths, OpenAI/Anthropic/embedding providers with fake clients, PII redaction,
  JWT, rate limiting.
* **API (httpx AsyncClient).** Auth flows, upload → analyze → get → ranking, idempotency
  and `force`, lazy LLM narrative on ranked matches without a score change, re-embedding
  on an embedding-model change, cascade delete, pagination, and 401/403/404/409/413/415/422/429.
* **Integration.** The Alembic migration matches the models (SQLite). On PostgreSQL the
  tests check the vector extension, `vector(512)` and the HNSW index, then run the full
  flow with pgvector pre-selection and a cascade delete.

LLMs are mocked at the provider interface. No test touches the network.

## Running Locally

```bash
cp .env.example .env                      # set JWT_SECRET (>= 32 chars)
uv venv && uv pip install -e ".[dev]"
uvicorn resume_matching.main:app_factory --factory --reload
# open http://localhost:8000/docs
```

By default this uses SQLite (`DB_CREATE_ALL=true`), the in-memory vector store and the
offline providers, so no keys are needed. To use real models:

```bash
pip install -e ".[openai,anthropic]"
LLM_PROVIDER=openai OPENAI_API_KEY=... EMBEDDING_PROVIDER=openai uvicorn ... --factory
```

Regenerate the binary samples with `python scripts/generate_sample_documents.py`. Recapture
the documented API responses with `python scripts/capture_api_examples.py`.

## Docker

```bash
cp .env.example .env
docker compose up --build        # db (pgvector/pgvector:pg16) -> migrate (alembic) -> api :8000
```

The image is multi-stage and runs as a non-root user with a `/health/live` healthcheck.
Migrations run in a one-shot `migrate` service before the API starts. (The Dockerfile was
not built in the authoring sandbox, which has no Docker daemon; CI builds it.)

## Example API Request

```bash
curl -s -X POST $API/api/matching/analyze \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"resumeId":"<resume id>","jobId":"<job id>"}'
```

## Example API Response

This is from a real run (`docs/api-examples.md`): the sample *Daniel Okafor* resume against
`samples/jobs/ai_backend_engineer.json`, offline providers. Arrays are abbreviated.

```json
{
  "success": true,
  "data": {
    "matchPercent": 89.3,
    "rawScore": 89.3,
    "verdict": "strong",
    "scoringVersion": "1.0.0+deeb6dad",
    "promptVersion": "match_explanation/v1",
    "knockouts": [],
    "skills": {
      "matchedRequired": [{"name": "Python", "importance": "critical", "matchType": "exact", "credit": 1.0, "evidenced": true, "lastUsed": "present"}],
      "missingNiceToHave": [{"name": "Terraform", "importance": "nice_to_have", "matchType": "missing", "credit": 0.0}]
    },
    "explanation": {
      "summary": "Scored 89.3/100 for 'Senior AI Backend Engineer (Python/FastAPI)': a strong match. The resume covers 16 of 17 required skills, with partial credit for 1 via related skills. Dated experience totals 8.4 years against 5+ required.",
      "gaps": ["Embeddings only indirectly covered by RAG.", "Missing nice-to-haves: Terraform and Kafka."],
      "source": "offline_template",
      "promptVersion": "match_explanation/v1"
    }
  },
  "message": null
}
```

Score breakdown for that run:

| Component | Score | Weight | Contribution | Evidence |
|---|---:|---:|---:|---|
| Required skills | 97.4 | 0.40 | 38.95 | 16/17 matched, 1 via related skills |
| Nice-to-have skills | 50 | 0.10 | 5.00 | 2/4 matched |
| Experience | 100 | 0.20 | 20.00 | 8.4 of 5+ years required |
| Role / title alignment | 76.2 | 0.10 | 7.62 | 'Senior Backend Engineer' vs 'Senior AI Backend Engineer (Python/FastAPI)' |
| Semantic similarity | 88.8 | 0.20 | 17.77 | best section: experience (raw cosine 0.405) |
| **Overall** | **89.3** | | | verdict: strong |

The `.NET` sample resume against the same JD has a raw score of 49.3. It is missing the
critical Python and FastAPI skills, so it is capped at **40.0**. Ranking the five samples
against the `.NET` JD puts that resume first (96.0). Three candidates tie at 40.0 and are
ordered by required-skill coverage. See [docs/scoring.md](docs/scoring.md).

## Future Enhancements

* Re-parse stored resumes when the taxonomy or parser version changes (versions are
  already stored).
* Redis-backed rate limiting and a job queue for very large ranking batches.
* LLM-assisted taxonomy suggestions with human approval, so the runtime stays
  deterministic.
* Calibrate semantic thresholds and weights against labelled recruiter decisions, and
  report adverse-impact metrics.
* OCR for scanned PDFs, and multi-language resumes.
* Organisation-level tenancy and per-job access control.

## Engineering Highlights

* **The score is a pure function.** `domain/` imports no framework, ORM or AI code. All
  scoring inputs are persisted (profile, analysis, vectors), so a result can be recomputed
  exactly. The trade-off: an LLM could catch nuance that rules miss. Related-skill credit
  and the semantic component narrow that gap without giving up reproducibility.
* **Versioning instead of silent drift.** The scoring version hashes the weights, the
  embedding model id and the taxonomy version. Idempotency is keyed on it, so a weight
  change cannot reuse stale results, and a provider change triggers re-embedding.
* **Grounding beyond the schema.** Schema validation alone doesn't stop a model from
  praising a skill the candidate lacks or from rounding 89.3 up to "90%". The checker
  cross-references every taxonomy skill and percentage in the prose against the facts.
* **Not-applicable components redistribute weight.** A JD without nice-to-haves or a
  minimum-years figure is not penalised. Knock-outs cap rather than zero, and `rawScore`
  is kept, so recruiters can see a strong profile held back by one must-have.
* **Boundary-aware regexes.** `\b` is wrong for `C#` and `.NET`. Custom look-arounds treat
  `+`, `#` and `.` as part of tokens. Ambiguous words are case-sensitive.
* **Ranking cost control.** Batch ranking is deterministic and LLM-free. Narratives are
  generated on demand when a recruiter opens a match. Above the pool size, pgvector's HNSW
  index pre-selects candidates.
* **One database for relational data and vectors.** This keeps cascading deletes and the
  privacy story simple. A separate vector DB is avoided until scale demands it (ADR 0003).
