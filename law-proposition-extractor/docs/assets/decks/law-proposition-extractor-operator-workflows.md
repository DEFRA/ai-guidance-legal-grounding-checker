---
marp: true
theme: gaia
paginate: true
headingDivider: 2
---

# Law Proposition Extractor — Operator workflows

Run, inspect, repair, review.

Source-of-truth: `docs/dev/`, `docs/reference/`, `README.md`.

## What operators actually do

1. Curate the **source registry** — register, refresh, and select legal sources for runs.
2. Run **proposition analysis** — single-jurisdiction inventory or comparison/divergence mode.
3. Inspect **runs and artifacts** — quality summary, extraction traces, repair signals.
4. Triage and **review** — record decisions across review layers.
5. Repair or rerun where needed; promote to **guidance-ready** under governance policy.

## Source registry and discovery

- CLI: `source-registry-list`, `source-registry-inspect`, `source-registry-register`, `source-registry-refresh`, `run-registry-sources`.
- API: `GET /ops/source-registry`, `POST /ops/source-registry/register`, `POST /ops/source-registry/search`, `POST /ops/source-registry/{registry_id}/refresh`.
- Run from registry: `POST /ops/runs/from-registry` (sync) · `POST /ops/run-jobs/from-registry` (async, preferred for the operator UI).

Discovery (evolving): `POST /ops/source-registry/{registry_id}/discover-related`, `POST /ops/source-registry/register-family-candidates`. Candidates are suggestions until registered.

## Source intake layers

- **Registered sources** — persistent registry entries, selectable for runs.
- **Source records in a run** — written to `sources.json` after ingestion.
- **Source-family candidates** — `source_family_candidates.json` — not analysed until registered.
- **Attached context** — audit/review metadata; not legal source input unless promoted.

See `docs/dev/source-registry.md`.

## Fragment selection modes

![width:1100](../generated/infographics/fragment-selection-modes.svg)

Pick the mode deliberately. The audit fields (`selected_for_extraction`, `selection_reason`, `skip_reason`) are written to `proposition_extraction_jobs.json` for every run regardless of mode.

## Extraction outcomes &amp; repair

![width:1100](../generated/infographics/extraction-repair-flow.svg)

Outcomes:

- Clean propositions
- Fallback-derived (`fallback_used = true`, `fallback_strategy = ...`)
- Repairable failure (`repairable = true`, `repair_reason`)
- Fail-closed (rows in `proposition_extraction_failures.json`)

Repair command:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline repair-extraction \
  --export-dir dist/static-report \
  --output-dir dist/static-report-repaired
```

Important flags: `--in-place`, `--only`, `--extraction-mode`, `--extraction-fallback`, `--use-llm`, `--retry-failed-llm`, `--derived-cache-dir`.

## Run quality

![width:1100](../generated/infographics/run-quality-explainer.svg)

- `pass`, `pass_with_warnings`, `fail` are quality-gate statuses, not legal approvals.
- `pass_with_warnings` is expected during extraction/review — triage rather than ignore.
- Inspect with `lint-export`:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export \
  --export-dir dist/static-report
```

## Review governance

![width:1100](../generated/infographics/review-governance-workflow.svg)

- Append-only `pipeline_review_decisions.json`.
- Decision values: `approved`, `rejected`, `needs_review`, `overridden`, `deferred`.
- Append a decision: `POST /ops/runs/{run_id}/pipeline-review-decisions` or CLI `add-review-decision`.
- `guidance-ready` is a promotion state earned through review — not default output.

See `docs/dev/review-governance.md`.

## Equine staged corpus

![width:1100](../generated/infographics/equine-staged-corpus-roadmap.svg)

Three staged profiles for interactive frontier extraction:

- `equine_passport_eu_2015_262_v0_1`
- `equine_passport_england_ukwide_v0_1`
- `equine_passport_devolved_v0_1`

Umbrella: `equine_passport_identification_v0_1` (batch-oriented). Coverage is staged — not a complete-corpus claim. See `docs/dev/equine-passport-staged-runs.md`.

## Common workflows (CLI)

```bash
# Run from a case and export (heuristic, provider-free)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline export-case \
  data/demo/example_case.json \
  --output-dir dist/static-report-tmp \
  --extraction-mode heuristic \
  --extraction-fallback mark_needs_review

# Run with model-backed extraction (requires LiteLLM and credit)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline export-case \
  data/demo/example_case.json \
  --output-dir dist/static-report \
  --extraction-mode local
```

## Inspecting a run

```bash
# 1) extraction job counts
jq '{
  total: length,
  selected: ([.[] | select(.selected_for_extraction == true)] | length),
  repairable: ([.[] | select(.repairable == true)] | length)
}' dist/static-report/proposition_extraction_jobs.json

# 2) quality/lint summary
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export \
  --export-dir dist/static-report

# 3) low-confidence extraction traces
jq '[.[] | select(.confidence == "low")] | length' \
  dist/static-report/proposition_extraction_traces.json

# 4) repairable extraction job rows
jq '[.[] | select(.repairable == true)]' \
  dist/static-report/proposition_extraction_jobs.json
```

## Dev reset (read the docs first)

- `clear-operations-runs` removes exported runs and keeps registry.
- `clear-operations-all` removes exported runs and clears registry + caches.

Always run with `--dry-run` first.

See `docs/dev/operations-state-reset.md`.

## Operational guardrails

- Lint pass is artifact integrity, not legal approval.
- `pass_with_warnings` is expected and should be triaged.
- Fallback / repairable / low-confidence rows require human review.
- `guidance-ready` is a promotion state after review/governance, not default output.
- Source family discovery is evolving and not a complete legal universe by default.

## References

- Operator reference: `docs/reference/cli.md`, `docs/reference/api-ops.md`, `docs/reference/artifacts.md`
- Dev guides: `docs/dev/source-registry.md`, `docs/dev/extraction-repair.md`, `docs/dev/review-governance.md`, `docs/dev/quality-runs.md`, `docs/dev/equine-passport-staged-runs.md`, `docs/dev/operations-state-reset.md`
- Roadmap: `docs/canonical/roadmap.md`
