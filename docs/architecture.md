# Architecture

## Components

```mermaid
flowchart TB
    subgraph API[FastAPI app]
        MW[Request-id middleware<br/>JSON logs + PII redaction]
        RT[Routers: auth, resumes, jobs,<br/>matching, candidates, health]
        DEP[Deps: JWT auth, roles,<br/>pagination, rate limiters]
    end
    subgraph SVC[Services]
        AS[AuthService]
        RSV[ResumeService]
        JS[JobService]
        MS[MatchingService]
    end
    subgraph DOM[Domain - pure, deterministic]
        PAR[Parsing: PDF/DOCX/TXT,<br/>sections]
        TAX[Skills taxonomy matcher]
        EXP[Experience + titles]
        JDA[JD analysis]
        SCO[Scoring engine + advice]
        RNK[Ranking]
    end
    subgraph AI[AI layer]
        EMB[EmbeddingProvider<br/>hashing / OpenAI]
        LLM[LLMProvider<br/>offline / OpenAI / Anthropic]
        EXPL[ExplanationGenerator<br/>validate + ground + fallback]
        PR[Versioned prompts]
    end
    subgraph DATA[Persistence]
        REPO[Repositories]
        VS[VectorStore<br/>PgVector / InMemory]
        DB[(PostgreSQL + pgvector<br/>SQLite in tests)]
    end
    RT --> DEP --> SVC
    RSV --> PAR & TAX & EXP & EMB
    JS --> JDA & EMB
    MS --> SCO & RNK & EXPL
    EXPL --> LLM & PR
    SVC --> REPO --> DB
    SVC --> VS --> DB
```

Dependencies point inward: `domain/` imports nothing from FastAPI, SQLAlchemy or the AI
layer, which keeps the scoring engine trivially unit-testable and deterministic.

## Analyze sequence

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as API (/api/matching/analyze)
    participant M as MatchingService
    participant D as DB
    participant S as Scoring engine
    participant E as ExplanationGenerator
    participant L as LLMProvider
    C->>A: POST {resumeId, jobId, force}
    A->>A: JWT + per-user token bucket (429)
    A->>M: analyze()
    M->>D: find(resume, job, scoring_version)
    alt exists and not force
        D-->>M: stored result
        M-->>A: 200 (idempotent replay)
    else compute
        M->>D: load profile, sections+vectors, job analysis
        M->>S: score_match(...) (pure)
        S-->>M: MatchComputation (score, breakdown, advice)
        M->>E: build_facts(computation) - no resume text, no PII
        loop up to 1 + LLM_VALIDATION_RETRIES
            E->>L: system + facts JSON
            L-->>E: JSON text
            E->>E: Pydantic validate + grounding (skills, numbers)
        end
        E-->>M: explanation (llm | template_fallback)
        M->>D: upsert match_results + ai_usage
        M-->>A: 201 Created
    end
    A-->>C: envelope {success, data, message}
```

## Ranking

`GET /api/candidates/ranking` loads the candidate pool (all resumes, or the top
`RANKING_CANDIDATE_POOL` by vector similarity when there are more), batch-computes any
missing matches for the current scoring version using the deterministic narrative
(`explanation.source = deferred_template`, no LLM calls), sorts with deterministic
tie-breaks (score, required coverage, semantic, upload time, id) and paginates. Opening a
batch result through `POST /api/matching/analyze` later attaches the LLM narrative without
touching the score.

## Persistence

```mermaid
erDiagram
    users ||--o{ resumes : uploads
    users ||--o{ jobs : creates
    resumes ||--o{ resume_sections : "has (cascade)"
    resumes ||--o{ match_results : "scored in (cascade)"
    jobs ||--o{ match_results : "scored in (cascade)"
    match_results ||--o{ ai_usage : "explained by"
```

* `resume_sections.embedding` and `jobs.embedding` are `vector(512)` on PostgreSQL (HNSW,
  `vector_cosine_ops`) and JSON arrays on SQLite via a `TypeDecorator`.
* JSON documents (`profile`, `analysis`, `result`, `explanation`) are JSONB on PostgreSQL.
* The Alembic migration is hand-written; `tests/integration/test_migrations.py` asserts it
  produces exactly the ORM's tables and columns, and the `postgres`-marked tests run it
  against a real pgvector database.

## Cross-cutting

* **Errors**: `AppError` subclasses map to status codes; a global handler renders
  `{success:false, message, errors[], traceId}` for app, validation, HTTP and unhandled
  errors.
* **Logging**: one JSON line per record with `request_id`; a logging filter redacts
  e-mails, phone numbers and profile URLs from messages, args and extras.
* **AI usage**: providers emit `UsageRecord`s (provider, model, prompt version, latency,
  tokens, estimated cost, success, attempt) into a context-scoped collector; the service
  persists them to `ai_usage`. No prompt or resume content is stored or logged.
