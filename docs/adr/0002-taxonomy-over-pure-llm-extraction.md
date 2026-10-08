# ADR 0002: Curated taxonomy for skill extraction instead of pure LLM extraction

* Status: accepted
* Date: 2026-10-08

## Context

Skill extraction feeds the largest scoring component. LLM extraction is flexible but
non-deterministic, costs tokens per resume, sends PII to a third party and can invent
skills. Naive keyword matching breaks on `Java` vs `JavaScript`, `C#`, `.NET`, `Node.js`.

## Decision

Use a versioned YAML taxonomy (`data/skills_taxonomy.yaml`, ~190 skills) with canonical
names, aliases, categories and symmetric related-skill links, compiled into one regex per
skill with token boundaries that treat `+`, `#` and `.` correctly. Ambiguous words (`Go`,
`Rust`, `Swift`, `SOLID`) are matched case-sensitively. Related links power partial credit
(Flask for FastAPI).

## Consequences

* Deterministic, fast (no network) and auditable: every match carries its surface form.
* Skills absent from the taxonomy are invisible unless the JD lists them explicitly
  (then they are matched literally). The taxonomy needs curation; its version is part of
  the scoring version.
* An LLM-assisted *suggestion* workflow for new taxonomy entries (human-approved) is a
  possible future enhancement that keeps the runtime deterministic.
