# Source registry and source-family discovery

## Purpose

The source registry is the controlled list of legal sources that may be selected for analysis runs.

Distinguish these layers:

- **registered sources**: persistent registry entries (`source-registry`) that can be selected for runs.
- **source records inside a run/export**: run-scoped artifacts written to `sources.json` after ingestion/execution.
- **source family candidates**: discovered related instruments (`source_family_candidates.json`) that are suggestions until registered.
- **attached context**: context-only rows/decisions used for audit/review; not analyzed as legal source input unless explicitly registered.

Operational rules:

- only registered **and selected** sources are analysed in a run.
- discovered candidates are **not** analysed until registered.
- attached context is audit/context metadata unless promoted into a registered source.

## Source registry lifecycle

### CLI

- `source-registry-list` — list registry entries.
- `source-registry-inspect` — inspect one registry entry.
- `source-registry-register` — register a new source reference (JSON/file input).
- `source-registry-refresh` — refresh one registered source.
- `run-registry-sources` — execute analysis using selected registry IDs.

### API

- `GET /ops/source-registry`
- `GET /ops/source-registry/{registry_id}`
- `POST /ops/source-registry/register`
- `POST /ops/source-registry/search`
- `POST /ops/source-registry/{registry_id}/refresh`
- `POST /ops/runs/from-registry` (sync)
- `POST /ops/run-jobs/from-registry` (async)

## Source-family discovery

Source-family candidates are related legal instruments discovered around a registry target source.

Discovery/registration routes:

- `POST /ops/source-registry/{registry_id}/discover-related`
- `POST /ops/source-registry/register-family-candidates`

Current candidate model supports roles/relationships/statuses such as:

- source roles: `corrigendum`, `annex`, `implementing_act`, `delegated_act`, `guidance`, `retained_version`, `base_act` (and others)
- inclusion statuses: `required_core`, `required_for_scope`, `optional_context`, `candidate_needs_review`, `excluded`

Scope caution:

- discovery is currently evolving and includes domain/fixture-oriented behavior in some paths.
- do not treat discovery output as complete legal universe coverage by default.

## Candidate registration decision model

The UI/helpers support decisions and classifications such as:

- already registered
- ready/auto-registerable
- needs source selection / manual review
- possible duplicate
- context only
- ignored

What operators should evaluate:

- **duplicate detection**: prefer authority + stable `authority_source_id` where available.
- **locator quality**: candidates lacking URL / stable authority locator / citation+CELEX+ELI may need manual review.
- **duplicate or near-duplicate rows**: possible duplicate checks include `authority_source_id`, CELEX/citation/url, and title similarity.
- **guidance/context rows**: guidance-only or conceptual grouping candidates should not be treated as legal source inputs unless deliberately promoted.

## Run-from-registry workflow

Typical flow:

1. select registered source IDs
2. set topic/cluster and analysis mode
3. optionally add subject tags
4. optionally tune extraction/quality options
5. run sync or enqueue async
6. inspect run quality and artifacts

### Async vs sync

- **Preferred for operator UI:** `POST /ops/run-jobs/from-registry`  
  Provides job status/events/progress tracking.
- **Synchronous/developer-oriented:** `POST /ops/runs/from-registry`  
  Runs inline and returns bundle payload directly.

## Relevant artifacts

| Artifact | Purpose |
|---|---|
| source registry path/config (`SOURCE_REGISTRY_PATH`) | Location of persisted registry JSON used by API/pipeline. |
| `sources.json` | Run-scoped source records that were actually ingested/used. |
| `source_family_candidates.json` | Candidate related instruments attached to run/export context. |
| source records in run (`run.json` + artifacts) | Run-level record of selected/analyzed sources and metadata. |
| `source_fetch_attempts.json` | Fetch diagnostics and attempt history for source retrieval. |
| `source_fragments.json` | Parsed fragments used for extraction selection/traceability. |
| `source_inventory.json` | Structured source inventory rows and analysis relationships. |
| `source_target_links.json` | Explicit source-to-source/linkage rows for analysis context. |

## Dev reset interaction

- `clear-operations-runs` removes exported runs and keeps registry.
- `clear-operations-all` removes exported runs and clears registry + caches.

See: [`docs/dev/operations-state-reset.md`](./operations-state-reset.md)

## Worked example (generic equine / 2016/429 pattern)

1. register base source (for example an AHL base instrument)
2. discover related candidates
3. register selected candidates
4. run from registry (sync or async)
5. inspect `source_family_candidates.json` and `sources.json` to verify what was discovered vs what was actually analyzed

This pattern supports staged expansion and auditability; it does not guarantee complete equine corpus coverage.

## Known limitations

- source discovery is evolving/domain-scoped.
- candidates can require manual review before registration.
- legal completeness still requires human/source analysis.
- guidance-only/context rows are not legal source inputs by default.
