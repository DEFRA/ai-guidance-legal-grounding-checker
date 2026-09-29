# `/ops` API reference

`/ops/*` is an operator/development surface used by the Law Proposition Extractor UI and CLI workflows. It is read-mostly with controlled mutations through explicit write routes. It is not a public stable external API contract unless explicitly promoted as such.

## Run inspection

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `GET /ops/runs` | read-only | List run catalog. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/runs/{run_id}` | read-only | Inspect one run. | `operations-inspector.tsx` |
| `GET /ops/runs/{run_id}/traces` | read-only | Return stage traces for run. | `operations-inspector.tsx` |
| `GET /ops/runs/{run_id}/review-decisions` | read-only | Return run review decisions. | `operations-inspector.tsx` |
| `GET /ops/divergence-assessments` | read-only | List divergence assessments. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/run-quality-summary` | read-only | Return run quality summary. | `proposition-explorer.tsx` |

## Source/proposition inspection

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `GET /ops/sources` | read-only | List source records. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/sources/{source_id}` | read-only | Inspect source detail. | `operations-inspector.tsx` |
| `GET /ops/sources/{source_id}/snapshots` | read-only | List source snapshots. | `operations-inspector.tsx` |
| `GET /ops/sources/{source_id}/timeline` | read-only | Source snapshot timeline view. | `operations-inspector.tsx` |
| `GET /ops/sources/{source_id}/history` | read-only | Source history across runs/registry. | `operations-inspector.tsx` |
| `GET /ops/sources/{source_id}/fragments` | read-only | Source fragment rows for source/run. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/source-fragments` | read-only | Filtered source fragment query. | `proposition-explorer.tsx` |
| `GET /ops/source-fetch-attempts` | read-only | Source fetch attempt diagnostics. | (none currently) |
| `GET /ops/source-parse-traces` | read-only | Source parse trace diagnostics. | (none currently) |
| `GET /ops/source-target-links` | read-only | Source target-link rows. | (none currently) |
| `GET /ops/effective/source-target-links` | read-only | Effective/merged source target links. | (none currently) |
| `GET /ops/effective/source-categorisation-rationales` | read-only | Effective source rationale rows. | (none currently) |
| `GET /ops/propositions` | read-only | List propositions. | `operations-inspector.tsx` |
| `GET /ops/effective/propositions` | read-only | Effective/merged propositions. | `proposition-explorer.tsx` |
| `GET /ops/effective-law-statements` | read-only | Effective law statement bundles (`presentation_role`, proposition composition). | `law-statements-explorer.tsx` |
| `GET /ops/proposition-matcher-law-candidates` | read-only | Proposition Matcher guidance-matching candidate queue. | `law-statements-explorer.tsx` |
| `GET /ops/proposition-extraction-traces` | read-only | Proposition extraction traces. | (none currently) |
| `GET /ops/effective/proposition-extraction-traces` | read-only | Effective extraction traces. | `proposition-explorer.tsx` |
| `GET /ops/proposition-completeness-assessments` | read-only | Completeness rows by run/proposition/status. | `proposition-explorer.tsx` |
| `GET /ops/legal-scopes` | read-only | Legal scope taxonomy rows. | `proposition-explorer.tsx` |
| `GET /ops/proposition-scope-links` | read-only | Scope links for propositions. | `proposition-explorer.tsx` |
| `GET /ops/legal-scopes/{scope_id}/propositions` | read-only | Propositions in scope (+ descendants option). | `proposition-explorer.tsx` |
| `GET /ops/proposition-groups` | read-only | Grouped proposition listing for explorer. | `proposition-explorer.tsx` |
| `GET /ops/proposition-groups/{group_id}` | read-only | Group detail payload for explorer. | `proposition-explorer.tsx` |
| `GET /ops/propositions/{proposition_key}/history` | read-only | Proposition history view. | `operations-inspector.tsx` |
| `GET /ops/divergence-findings/{finding_id}/history` | read-only | Divergence finding history view. | `operations-inspector.tsx` |
| `GET /ops/corpus-coverage/equine` | read-only | Equine coverage + readiness summary. | `operations-inspector.tsx` |

## Review decisions

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `GET /ops/pipeline-review-decisions` | read-only | Query pipeline review decision rows. | `proposition-explorer.tsx` |
| `POST /ops/runs/{run_id}/pipeline-review-decisions` | mutating | Append pipeline review decision row for run artifact. | `proposition-explorer.tsx`, `operations-inspector.tsx` |

## Source registry

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `GET /ops/source-registry` | read-only | List registry entries. | `operations-inspector.tsx` |
| `GET /ops/source-registry/{registry_id}` | read-only | Inspect registry entry. | `operations-inspector.tsx` |
| `POST /ops/source-registry/register` | mutating | Register source reference. | `operations-inspector.tsx` |
| `POST /ops/source-registry/search` | mutating | Search source provider and return candidates. | `operations-inspector.tsx` |
| `POST /ops/source-registry/{registry_id}/discover-related` | mutating | Discover related family candidates for registry source. | `operations-inspector.tsx` |
| `POST /ops/source-registry/register-family-candidates` | mutating | Register selected family candidates. | `operations-inspector.tsx` |
| `POST /ops/source-registry/{registry_id}/refresh` | mutating | Refresh one registry entry. | `operations-inspector.tsx` |

## Async run jobs

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `POST /ops/run-jobs/from-registry` | mutating | Queue registry-based pipeline run job. | `operations-inspector.tsx` |
| `POST /ops/run-jobs/compare-proposition-datasets` | mutating | Queue dataset comparison job. | `operations-inspector.tsx` |
| `POST /ops/run-jobs/equine-corpus` | mutating | Queue equine corpus workflow job. | `operations-inspector.tsx` |
| `GET /ops/run-jobs` | read-only | List queued/running/completed jobs. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/run-jobs/{job_id}` | read-only | Inspect one async job. | `operations-inspector.tsx`, `proposition-explorer.tsx` |
| `GET /ops/run-jobs/{job_id}/events` | read-only | Stream/list job event timeline. | `operations-inspector.tsx`, `proposition-explorer.tsx` |

## Dev reset

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `POST /ops/dev/clear/runs` | mutating | Remove run exports while preserving registry. | `operations-inspector.tsx` |
| `POST /ops/dev/clear/all` | mutating | Remove exports, registry, source cache, derived cache. | `operations-inspector.tsx` |

## Repair/corpus jobs

| Route | Type | Purpose | UI consumer |
|---|---|---|---|
| `POST /ops/run-jobs/repair-extraction` | mutating | Repair extraction for run/export target and emit repaired bundle. | `proposition-explorer.tsx` |
| `POST /ops/runs/from-registry` | mutating | Synchronous run-from-registry path (returns run bundle). | (none currently) |
