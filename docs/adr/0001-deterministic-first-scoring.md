# ADR 0001: Deterministic-first scoring; the LLM only narrates

* Status: accepted
* Date: 2026-10-08

## Context

Recruiters need to compare candidates and defend decisions. An LLM asked "how well does
this resume match?" gives numbers that drift with phrasing, temperature, model version and
prompt changes, cannot be audited, and can absorb protected attributes from the raw text.

## Decision

* The match score is computed by a pure, versioned scoring engine (skill coverage,
  experience curve, title/seniority, calibrated embedding similarity, knock-outs) with all
  weights in configuration.
* The LLM receives only the computed facts (no resume text) and returns a structured
  explanation that is validated with Pydantic and checked for grounding: no skills outside
  the facts, no percentages other than the computed ones. Failures are retried with the
  errors fed back, then replaced by a deterministic template.
* Every result stores `scoring_version` and `prompt_version`.

## Consequences

* Scores are reproducible, explainable per component and testable without a network.
* The engine misses nuance an LLM could catch (e.g. equivalent experience described in
  unusual words); the semantic component and related-skill credit partially compensate.
* Changing weights is a config change, but it creates a new scoring version and results
  are recomputed rather than reused.
