# ADR 0003: PostgreSQL + pgvector for embeddings

* Status: accepted
* Date: 2026-10-08

## Context

We store one embedding per scored resume section and per job, need cosine similarity for
scoring and nearest-neighbour retrieval to pre-select a ranking pool, and must delete all
of a candidate's data on request.

## Decision

Store vectors in PostgreSQL with pgvector (`vector(EMBEDDING_DIM)`, HNSW index with
`vector_cosine_ops`) next to the relational data, behind a `VectorStore` protocol.
`PgVectorStore` queries the index; `InMemoryVectorStore` (numpy) serves SQLite-based tests
and local runs.

## Consequences

* One database, one transaction, `ON DELETE CASCADE` removes vectors with the resume -
  simpler privacy story than syncing a separate vector database.
* The vector dimension is fixed in the schema; changing `EMBEDDING_DIM` requires a
  migration. Embeddings carry the model id, and a model change triggers re-embedding and
  a new scoring version.
* At very large scale a dedicated vector store might be preferable; the protocol keeps
  that swap local to one class.
