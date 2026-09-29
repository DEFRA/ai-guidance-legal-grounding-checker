# ADR-0009: Preserve provenance and time/version context for legal sources

## Status

Accepted

## Context

Source models and intake already capture provenance, `as_of_date`, `retrieved_at`, `content_hash`, `version_id`, snapshots, and fragments. Comparison runs store source record/snapshot/fragment identifiers to keep traceability across artifacts.

## Decision

Every source used for analysis must carry explicit provenance and time/version-aware metadata, with immutable snapshot references used by downstream propositions and runs.

## Consequences

Assessments are auditable against the legal text state that existed at analysis time, supporting reproducibility and later challenge/review. Data ingestion is stricter and requires complete source metadata rather than anonymous text blobs.

Source-derived proposition lineage keys (`proposition_key`) are anchored on registered instrument and fragment identifiers (ADR-0018), not on interpretive categories alone.
