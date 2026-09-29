# Law Proposition Extractor

Law Proposition Extractor is a source-first, proposition-first legal analysis workbench. It supports single-jurisdiction proposition analysis as a first-class workflow, with divergence analysis downstream when comparison mode is enabled. Runs produce source-backed artifacts (records, snapshots, fragments, propositions, traces, quality summaries), and human review decisions are part of the operational workflow.

## Current maturity / status

- **implemented/tested:** source registry, registry/case runs, fragment-level extraction, proposition explorer grouping, async run jobs, run quality summary, typed legal relationships / effective-law context, DecisionExplanations + Workbench Why panel, offline Article 49a acceptance.
- **operator-friendly gaps:** some command/API/artifact contracts are richer than older docs; see `docs/explainability/` for the current explainability handbook.
- **experimental/evolving:** source-family discovery behavior and some artifact schemas around extraction diagnostics/repair metadata.
- **pending legal review:** extracted propositions are review datasets; they are not legally approved conclusions by default.

Important interpretation rules:

- lint pass means artifact integrity / quality-gate pass, not legal approval.
- `pass_with_warnings` is expected during extraction/review and should be triaged, not ignored.
- `guidance-ready` is a promotion state after review/governance, not default output.

## Core concepts

- **source registry:** persisted list of tracked legal source references used for repeatable runs.
- **source record:** run-level source identity and metadata row (`sources.json`).
- **source snapshot:** fetched/versioned source text instance tied to provenance/content hash.
- **source fragment:** article/annex/section/chunk subdivision used for extraction targeting.
- **proposition:** atomic legal statement extracted from source text/fragments.
- **proposition extraction trace:** per-proposition provenance/diagnostic trace for how extraction happened.
- **proposition extraction job:** per-source/fragment extraction attempt row including selection, LLM/fallback/repair flags.
- **scope link:** deterministic link between propositions and legal scope taxonomy.
- **run quality summary:** lint/quality-gate aggregate (`pass`, `pass_with_warnings`, `fail`) with metrics/recommendations.
- **review decision:** append-only governance decision on a run artifact (e.g., proposition, scope links, completeness row).

## Common workflows

### A) Run from a case and export (provider-free / default onboarding path)

`run-bundle` writes the materialised case with `--output`; `export-case` writes the static bundle with `--output-dir` (or `--output` as an alias).

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline export-case \
  data/demo/example_case.json \
  --output-dir dist/static-report-tmp \
  --derived-cache-dir "$(mktemp -d)" \
  --extraction-mode heuristic \
  --extraction-fallback mark_needs_review \
  --divergence-reasoning none
```

### A.2) Run from a case with model-backed extraction (Requires configured LiteLLM/local model)

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline export-case \
  data/demo/example_case.json \
  --output-dir dist/static-report \
  --extraction-mode local
```

`--extraction-mode local` and `--extraction-mode frontier` call configured model endpoints via the LiteLLM proxy (`just litellm`). With `run-bundle --use-llm`, the default `--extraction-fallback` is **`fail_closed`** (no silent heuristic substitution). See [`docs/dev/llm-extraction-local-mode.md`](docs/dev/llm-extraction-local-mode.md) for service wiring and the `400 No connected db.` LiteLLM error.

### A.3) Offline Article 49a legal-structure acceptance (no network / LLM / secrets)

Deterministic end-to-end regression for the Article 49a vertical slice (structural frontier →
propositions → groups → typed relationships → effective law → Proposition Matcher → source effects →
Workbench view models). Fixture: `tests/fixtures/article_49a_legal_structure/`.

```bash
just test-acceptance-article-49a
# equivalent:
uv run --all-packages pytest tests/acceptance/test_article_49a_legal_structure.py \
  tests/acceptance/test_article_49a_legal_structure_mutations.py -q
npm --prefix apps/web test -- lib/article-49a-acceptance.test.ts
```

Included in the default `just test` / `uv run --all-packages pytest` suite via `tests/acceptance/`.

### B) Build staged equine passport profile (EUR 2015/262, requires model credentials/configuration for `--use-llm`)

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline build-equine-corpus \
  --corpus-config examples/corpus_equine_passport_eu_2015_262_v0_1.json \
  --output-dir dist/static-report \
  --use-llm
```

### C) Lint exported output

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export \
  --export-dir dist/static-report
```

### D) Clear operations state (dry-run then confirm)

```bash
# clear run bundles only (keep registry)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-runs --dry-run
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-runs --confirm

# clear bundles + registry + caches
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-all --dry-run
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline clear-operations-all --confirm
```

## Running services

```bash
# API (FastAPI, default 127.0.0.1:8010)
just api

# Web app (Next.js)
just web
```

If needed, point web to a non-default API:

```bash
export NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_API_BASE_URL=http://127.0.0.1:8010
```

See `apps/web/README.md` for current web workbench scope.

## Important output artifacts

| Artifact | Purpose |
|---|---|
| `sources.json` | Source records used/produced in the run. |
| `source_fragments.json` | Fragment inventory (article/annex/section/chunk) used for extraction targeting. |
| `propositions.json` | Extracted proposition dataset for review and downstream comparison. |
| `proposition_extraction_traces.json` | Per-proposition extraction provenance and diagnostics. |
| `proposition_extraction_jobs.json` | Per extraction job rows (selection, invocation, fallback, repairability metadata). |
| `extraction_llm_call_traces.json` | Chunk/model-level LLM call diagnostics and context-window signals. |
| `run_quality_summary.json` | Run-level quality gate status, counts, metrics, and recommendations. |
| `equine_source_coverage.json` | Equine corpus source coverage matrix snapshot (pending review status). |
| `equine_proposition_coverage.json` | Equine corpus proposition coverage matrix snapshot (pending review status). |
| `equine_corpus_readiness.json` | Equine readiness summary, including source-universe context when available. |
| `runs/<run>/traces/*.json` | Stage-by-stage run trace records for auditability. |
| `runs/_jobs/<job>/events.json` | Async job progress events (stage/status/message/metrics timeline). |

## How to inspect a run

```bash
# 1) extraction job counts
jq '{
  total: length,
  selected: ([.[] | select(.selected_for_extraction == true)] | length),
  repairable: ([.[] | select(.repairable == true)] | length)
}' dist/static-report/proposition_extraction_jobs.json

# 2) quality/lint summary
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export --export-dir dist/static-report

# 3) low-confidence extraction traces
jq '[.[] | select(.confidence == "low")] | length' dist/static-report/proposition_extraction_traces.json

# 4) repairable extraction job rows
jq '[.[] | select(.repairable == true)]' dist/static-report/proposition_extraction_jobs.json
```

## LLM / model configuration

- Extraction modes: `heuristic` (deterministic/no model), `local`, `frontier`.
- Law Proposition Extractor uses a LiteLLM/OpenAI-compatible endpoint for configured model aliases.
- `local`/`frontier` modes call model endpoints and may fallback when model calls fail or are unavailable, depending on fallback policy.
- Key environment variables:
  - `LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL`
  - `LAW_PROPOSITION_EXTRACTOR_LLM_API_KEY`
  - `LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_EXTRACT`
- Provider credentials are configured behind LiteLLM (e.g., Anthropic/OpenAI) and are only needed for model-enabled workflows.
- Model keys are **not required** for all workflows (heuristic and many inspection/lint flows run without them).

## Documentation map

- Architecture and pipeline:
  - Pipeline overview: `docs/architecture/pipeline-overview.md`
  - System overview: `docs/architecture/system-overview.md`
  - Artifact map: `docs/reference/artifacts.md`
- Operator guides (`docs/dev/`):
  - `source-registry.md`, `fragment-selection-and-corpus-profiles.md`, `extraction-repair.md`, `quality-runs.md`, `review-governance.md`, `equine-passport-staged-runs.md`, `operations-state-reset.md`, `jurisdiction-analysis-runs.md`, `article-109-equine-pilot.md`
- Reference (`docs/reference/`):
  - `cli.md`, `api-ops.md`, `artifacts.md`
- Web workbench: `apps/web/README.md`
- Roadmap: `docs/canonical/roadmap.md`, `docs/roadmap/v1.md`

### Visual assets

Generated visuals are committed alongside their sources. Regenerate with `just diagrams`, `just infographics`, `just decks`, or `just docs-refresh` for everything.

- Architecture diagrams (D2 sources, committed SVGs): [`docs/assets/diagrams/README.md`](docs/assets/diagrams/README.md)
- Infographic index (titles, purposes, source/generated paths, thumbnails): [`docs/assets/infographics/README.md`](docs/assets/infographics/README.md)
- Stakeholder / architecture / operator decks (Marp sources, committed HTML/PDF/PPTX): [`docs/assets/decks/README.md`](docs/assets/decks/README.md)
- Generated infographic SVG + PNG outputs: [`docs/assets/generated/infographics/`](docs/assets/generated/infographics/)
- Generated deck HTML + PDF + PPTX outputs: [`docs/assets/generated/decks/`](docs/assets/generated/decks/)
- Generated assets inventory and commit policy: [`docs/assets/generated-assets.md`](docs/assets/generated-assets.md)

Key generated infographic PNGs (rendered at 1600×900):

- Pipeline overview: [`docs/assets/generated/infographics/pipeline-overview.png`](docs/assets/generated/infographics/pipeline-overview.png)
- Artifact map: [`docs/assets/generated/infographics/artifact-map.png`](docs/assets/generated/infographics/artifact-map.png)
- Extraction repair flow: [`docs/assets/generated/infographics/extraction-repair-flow.png`](docs/assets/generated/infographics/extraction-repair-flow.png)
- Fragment selection modes: [`docs/assets/generated/infographics/fragment-selection-modes.png`](docs/assets/generated/infographics/fragment-selection-modes.png)
- Review governance workflow: [`docs/assets/generated/infographics/review-governance-workflow.png`](docs/assets/generated/infographics/review-governance-workflow.png)
- Equine staged corpus roadmap: [`docs/assets/generated/infographics/equine-staged-corpus-roadmap.png`](docs/assets/generated/infographics/equine-staged-corpus-roadmap.png)
- Run quality explainer: [`docs/assets/generated/infographics/run-quality-explainer.png`](docs/assets/generated/infographics/run-quality-explainer.png)

## Known limitations

- Source-family discovery is still scoped/evolving.
- Artifacts are rich, but some schemas are still evolving.
- Human legal review is required before relying on extracted propositions.
- Some workflows require LLM provider credentials.
- Broader equine corpus coverage is staged and not complete.
