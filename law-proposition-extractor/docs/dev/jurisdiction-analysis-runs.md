# Jurisdiction analysis runs and dataset comparison

## Terms

- **Analysis run** — Pipeline execution that ingests sources and **extracts propositions**. Its durable output is a **proposition dataset** (propositions + sources + traces + `proposition_dataset` metadata on export).
- **Proposition dataset** — Named, auditable snapshot: `dataset_id`, `run_id`, `jurisdiction_scope` (`EU` | `UK` | `mixed` | `unknown`), `source_ids`, optional `corpus_id`, extraction settings, `created_at`, quality status (`proposition_dataset.json` after export).
- **Comparison run** (dataset level) — Takes **two** existing datasets (`left_run_id`, `right_run_id`), merges their exported artifacts, runs **pairing + divergence only** (`skip_proposition_extraction`), and records `dataset_comparison_run` on the new bundle. It must not call proposition extractors again.
- **View mode** (Propositions UI) — Client-side filters (`jview` query / View chips): EU, UK, EU+UK grouped, Divergences. These only change display; they do not POST analysis jobs.

## Registry configuration

`RegistryRunRequest.analysis_scope`:

- `selected_sources` — Exactly the ticked registry rows (default). For `analysis_mode: divergence` with **multiple** jurisdictions, you must set `comparison_jurisdiction_a` and `comparison_jurisdiction_b` (no silent EU/UK default).
- `eu` / `uk` — Filter the tick list to that jurisdiction before extraction.
- `eu_uk` — Keep only EU and UK-labelled rows; for divergence, pairing defaults to EU vs UK when both exist.

`analysis_mode: auto` no longer enables divergence from jurisdiction count alone; use `divergence` explicitly.

## Identical `content_hash`

When two source snapshots (or fragments) share the same `content_hash`, the pipeline may **reuse** the first successful extraction’s proposition rows for later jobs, cloning them with the target `source_record_id`, `source_snapshot_id`, jurisdiction, citation, and a final `judit_extraction_reuse:{…}` JSON line in `notes` (see `attach_judit_extraction_reuse`). Provenance is not collapsed: each source keeps its own record and snapshot identity.

Reuse is **durable** across runs that share the same `--derived-cache-dir` (stage `proposition_extraction_content_hash`), not only within a single run.

## API

- `POST /ops/run-jobs/compare-proposition-datasets` — Queue a dataset comparison job (`ComparePropositionDatasetsRequest`).

## ADR / identity

Proposition identity and naming rules are unchanged (see ADR-0018). This document only adds orchestration and metadata around existing extraction and divergence stages.
