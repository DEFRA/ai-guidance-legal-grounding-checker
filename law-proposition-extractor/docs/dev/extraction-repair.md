# Extraction repair and failure handling

## Purpose

Extraction runs can produce a mix of outcomes:

- clean propositions (model/deterministic path succeeds)
- fallback-derived propositions
- repairable failures
- low-confidence traces
- fail-closed outcomes

![Extraction fallback and repair flow diagram](../assets/generated/diagrams/extraction-repair-flow.svg)

Diagram source: `docs/assets/diagrams/extraction-repair-flow.d2` (generated SVG may be absent in a clean checkout; run `just diagrams`).

Operational guardrails:

- `repairable != accepted`; it means "eligible for repair workflow", not legally accepted output.
- fallback output is review material, not legal approval.
- lint/quality pass checks artifact integrity and quality gates, not legal correctness.

## Key artifacts

| Artifact | What it captures |
|---|---|
| `proposition_extraction_jobs.json` | Per source/fragment extraction job row: selection, model invocation, fallback, repairability, parse diagnostics. |
| `proposition_extraction_traces.json` | Per proposition extraction provenance (method, confidence, warnings/errors, source lineage). |
| `extraction_llm_call_traces.json` | LLM/chunk diagnostics including token estimates, cache hints, context-window risk, parse-error metadata. |
| `proposition_extraction_failures.json` | Fail-closed/failure rows, including validation issues and failure reason. |
| `run_quality_summary.json` | Run-level quality status (`pass`, `pass_with_warnings`, `fail`) and aggregated metrics. |

## Important fields

| Field | Typical artifact | Meaning |
|---|---|---|
| `selected_for_extraction` | `proposition_extraction_jobs.json` | Whether the job was actually selected to run extraction. |
| `selection_reason` | `proposition_extraction_jobs.json` | Why the fragment/source was selected (or marked skipped by policy path). |
| `skip_reason` | `proposition_extraction_jobs.json` | Why extraction was skipped for this job. |
| `extraction_mode` | jobs/traces/failures | `heuristic`, `local`, or `frontier` execution mode. |
| `model_alias` | jobs/traces/failures/llm traces | Model alias used (if model path was attempted). |
| `estimated_input_tokens` | jobs/llm traces | Estimated prompt/chunk size used for planning and diagnostics. |
| `llm_invoked` | jobs/llm traces | Whether a model endpoint call was actually made. |
| `fallback_used` | jobs/traces | Whether fallback logic produced/modified output. |
| `fallback_strategy` | jobs/traces | Strategy used for fallback path (for example definition extractor path). |
| `repairable` | `proposition_extraction_jobs.json` | Job marked as repair-target candidate. |
| `repair_reason` | `proposition_extraction_jobs.json` | Classified repair reason for triage/repair flow. |
| `raw_model_output_excerpt` | `proposition_extraction_jobs.json` | Redacted/truncated snippet of invalid model output for debugging parse failures. |
| `raw_model_output_truncated` | `proposition_extraction_jobs.json` | Indicates whether excerpt was truncated. |
| `parse_error_message` | jobs/llm traces | JSON parse or model-output parse error summary. |
| `parse_error_line` | jobs/llm traces | Line number of parse failure when available. |
| `parse_error_column` | jobs/llm traces | Column number of parse failure when available. |
| `confidence` | `proposition_extraction_traces.json` | Trace confidence (`high`, `medium`, `low`) used for review prioritization. |
| `validation_errors` | traces/failures | Validation error list captured during extraction/fallback processing. |

## Failure and fallback modes

### `extraction_fallback`

- `fallback`  
  Use fallback path to keep producing review material when model path fails/returns invalid output.
- `mark_needs_review`  
  Preserve output with explicit review-oriented signaling for downstream triage.
- `fail_closed`  
  Record failure rows instead of silently accepting weak output; intended for stricter runs.

### `model_error_policy`

- `continue_with_fallback`  
  Default tolerant behavior: keep processing with fallback path when possible.
- `continue_repairable`  
  Continue pipeline while preserving repairable diagnostics for later re-run/triage.
- `stop_repairable`  
  Halt remaining extraction jobs after a repairable model failure event; downstream jobs are marked skipped by policy.

If exact behavior is critical for a run mode, verify current CLI/API behavior with `--help` and run artifacts.

## Definition fallback

Definition provisions are handled with a deterministic definition extractor fallback path (for example Article 2-style "Definitions" sections).

- Why: definition-heavy clauses often need structured handling even when model JSON parsing fails.
- When triggered: fallback path detects definition-like content and switches to deterministic extraction.
- How it appears: job/trace metadata can show `fallback_strategy=definition_extractor`.
- Review requirement: even deterministic definition fallback output still requires legal/human review, especially if triggered after a model parse failure.

## Inspection commands

```bash
# Count selected/invoked/skipped jobs
jq '{
  total: length,
  selected: ([.[] | select(.selected_for_extraction == true)] | length),
  llm_invoked: ([.[] | select(.llm_invoked == true)] | length),
  skipped: ([.[] | select(.selected_for_extraction == false)] | length)
}' dist/static-report/proposition_extraction_jobs.json

# List repairable jobs
jq '.[] | select(.repairable == true)' dist/static-report/proposition_extraction_jobs.json

# Inspect low-confidence traces
jq '.[] | select(.confidence == "low")' dist/static-report/proposition_extraction_traces.json

# List fallback-derived propositions (trace-level)
jq '.[] | select((.fallback_used == true) or (.extraction_method == "fallback"))' \
  dist/static-report/proposition_extraction_traces.json

# Inspect parse error excerpts safely (keep only diagnostics)
jq '.[] | select(.parse_error_message != null) | {
  id,
  source_record_id,
  source_fragment_id,
  parse_error_message,
  parse_error_line,
  parse_error_column,
  raw_model_output_excerpt,
  raw_model_output_truncated
}' dist/static-report/proposition_extraction_jobs.json

# Inspect fragmentary propositions via completeness assessments
jq '.proposition_completeness_assessments[]? | select(.status == "fragmentary")' \
  dist/static-report/proposition_completeness_assessments.json
```

## Repair command

Primary command:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline repair-extraction \
  --export-dir dist/static-report \
  --output-dir dist/static-report-repaired
```

Important options:

- `--export-dir`
- `--output-dir`
- `--in-place`
- `--only`
- `--extraction-mode`
- `--extraction-fallback`
- `--use-llm`
- `--retry-failed-extraction-cache` / `--no-retry-failed-extraction-cache` (alias: `--retry-failed-llm`)
- `--ignore-failed-extraction-cache` (reuse cached chunk failures without LLM calls)
- `--derived-cache-dir`
- `--quiet` / `--verbose`

For exact current semantics and constraints, check:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline repair-extraction --help
```

## Worked example pattern (Article 2 / definitions)

One common pattern in regulation definitions sections (for example Article 2-style clauses) is:

- frontier model call returns invalid JSON for a chunk
- `fallback_used=true`
- `fallback_strategy=definition_extractor`
- `repairable=true`
- `raw_model_output_excerpt` captured with truncation flag when needed
- resulting propositions still produced as definition-style rows (for review)

This is a pattern, not a guaranteed outcome for every run.

## Review guidance

Recommended human review flow:

1. inspect repairable jobs (`proposition_extraction_jobs.json`)
2. inspect fallback-derived proposition traces
3. inspect low-confidence traces
4. record review decisions (UI/API/CLI review decision flows)
5. rerun lint/quality summary
6. promote to `guidance-ready` only after accepted review decisions under your governance policy
