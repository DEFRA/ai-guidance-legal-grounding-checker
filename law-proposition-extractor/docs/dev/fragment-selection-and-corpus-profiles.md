# Fragment selection and corpus profiles

## Purpose

Large legal instruments are split into fragments, and corpus profiles control which fragments are extracted into propositions.

Fragment granularity can include:

- articles (`article:1`, `article:2`)
- annexes (`annex:i`)
- sections (`section:...`)
- chunks (`article:2|chunk:001`) when chunked extraction is active
- full documents (`document:full`) when no finer segmentation is available

Not every fragment should be sent to an LLM. Fragment selection is an explicit quality/cost/governance control:

- quality: reduce noisy proposition extraction from irrelevant clauses
- cost: reduce model calls and token usage
- governance: keep staged runs reviewable and auditable

## Fragment lifecycle

Extraction artifacts are linked through a fragment lifecycle:

1. `source record`  
   Legal source identity row (`sources.json`) with authoritative locator/title/metadata.
2. `source snapshot`  
   Fetched/versioned source text instance tied to provenance and content hash (`source_snapshots.json`).
3. `source fragment`  
   Subdivision row (`source_fragments.json`) for article/annex/section/chunk/document units.
4. `fragment locator`  
   Canonical address used for selection and audit, for example `article:1`, `annex:i`, `section:part-2/chapter-1`.
5. `fragment type`  
   Normalized fragment class (`article`, `annex`, `section`, `chunk`, `document`, etc.).
6. `source_fragment_id`  
   Stable fragment row identifier used to join extraction jobs and proposition traces.
7. `fragment-level extraction jobs`  
   One job row per source+fragment in `proposition_extraction_jobs.json`, including selection decision, invocation, fallback, and proposition counts.

## Fragment selection modes

![Fragment selection modes diagram](../assets/generated/diagrams/fragment-selection-modes.svg)

Diagram source: `docs/assets/diagrams/fragment-selection-modes.d2` (generated SVG may be absent in a clean checkout; run `just diagrams`).

### `required_only`

Behavior:

- selects `required_fragment_locators`
- selects annexes explicitly listed as required
- does **not** select focus-term matches outside required locators

When to use:

- staged profile runs
- legal review batches where scope must stay tight
- cost-controlled baseline runs

Risks:

- may omit legally relevant provisions if required locators are incomplete
- can under-cover contextual duties/definitions outside required set

Expected proposition count behavior:

- typically lowest proposition count of the three modes
- count variability still depends on model/version/chunking/fallback configuration

### `required_plus_focus`

Behavior:

- selects required locators
- additionally selects fragments with strong focus-term matches

When to use:

- exploratory expansion around a curated legal core
- staged-plus-discovery passes where you want broader capture without full sweep

Risks:

- focus-term matching may overselect noisy fragments
- higher review burden than `required_only`

Expected proposition count behavior:

- usually higher than `required_only`
- usually lower than broad all-fragment extraction

### `all_matching`

Behavior:

- current broad extraction behavior
- keeps broad matching paths active (including non-focus fallback selection paths)

When to use:

- initial exploration
- recall-oriented sweeps before curation hardening

Risks:

- can be noisy and costly
- can generate proposition overload for review workflows

Expected proposition count behavior:

- typically highest proposition volume
- can produce high variance by source text shape and chunking

## Selection config fields

Primary profile fields:

- `fragment_selection_mode`: `required_only`, `required_plus_focus`, `all_matching`
- `required_fragment_locators`: explicit canonical locators operators require
- `focus_terms`: term list used for fragment matching in modes that permit focus matching
- `include_annexes`: include annex fragments even when not in required list
- `focus_scopes`: semantic focus guidance for proposition relevance/scoping
- `max_propositions_per_source`: extraction cap per source
- `extraction_mode`: extraction execution mode (`heuristic`, `local`, `frontier`)
- `extraction_fallback`: fallback behavior when model output fails/invalid
- `model_error_policy`: continue/repair/stop strategy for model failures
- `divergence_reasoning`: divergence reasoning mode (typically `none` for staged extraction runs)

Important distinction:

- `focus_scopes`: guides proposition/scope relevance once extraction runs
- `focus_terms`: used for fragment text matching where selection mode allows it
- `required_fragment_locators`: explicit legal/operator inclusion set, independent of term matching

## Job audit fields

Use `proposition_extraction_jobs.json` to audit selection and extraction behavior.

Key fields:

- `selected_for_extraction`: whether fragment job was selected
- `selection_reason`: why selected (or why policy path skipped)
- `skip_reason`: normalized skip reason
- `llm_invoked`: whether model call was actually made
- `proposition_count`: extracted proposition count linked to that job
- `repairable`: whether job is flagged for repair workflow
- `fallback_strategy`: fallback path used (for example `definition_extractor`)
- `estimated_input_tokens`: pre-call token estimate for extraction payload
- `context_window_risk`: context-limit risk flag

Inspection examples:

```bash
# count selected/invoked/skipped
jq '{
  total: length,
  selected: ([.[] | select(.selected_for_extraction == true)] | length),
  llm_invoked: ([.[] | select(.llm_invoked == true)] | length),
  skipped: ([.[] | select(.selected_for_extraction == false)] | length)
}' dist/static-report/proposition_extraction_jobs.json

# list selected fragments
jq '.[] | select(.selected_for_extraction == true) | {
  source_record_id,
  source_fragment_id,
  fragment_locator,
  fragment_type,
  selection_reason
}' dist/static-report/proposition_extraction_jobs.json

# list skipped fragments with reasons
jq '.[] | select(.selected_for_extraction == false) | {
  source_record_id,
  source_fragment_id,
  fragment_locator,
  selection_reason,
  skip_reason
}' dist/static-report/proposition_extraction_jobs.json

# list noisiest fragments by proposition_count
jq 'sort_by(.proposition_count // 0) | reverse | .[:20] | .[] | {
  source_record_id,
  source_fragment_id,
  fragment_locator,
  proposition_count,
  llm_invoked,
  repairable
}' dist/static-report/proposition_extraction_jobs.json
```

## Staged passport profile example

Reference staged profile:

- profile file: `examples/corpus_equine_passport_eu_2015_262_v0_1.json`
- `fragment_selection_mode`: `required_only`
- required locator set includes a targeted subset such as `article:1`, `article:2`, `article:4`, ... and annexes `annex:i`, `annex:ii`, `annex:iii`

Operational expectations:

- selected fragments should stay close to required locator coverage
- non-required fragments should mostly appear as skipped in job audit
- Article 2 definition fallback may appear (`fallback_strategy=definition_extractor`) if frontier JSON parsing fails
- this profile is staged and intentionally not complete equine-law coverage

Proposition counts are **not guaranteed constants**. They vary by model, model version, chunking, prompt behavior, and fallback/repair settings.

## Corpus profile workflow

Typical operator flow:

1. estimate run size (optional but recommended for broad profiles)
2. build corpus
3. lint export
4. inspect extraction jobs
5. inspect run quality
6. review propositions

Commands:

```bash
# optional estimate
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline estimate-corpus-run \
  examples/equine_source_universe.json \
  --profile equine_passport_eu_2015_262_v0_1 \
  --fetch

# build corpus
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline build-equine-corpus \
  --corpus-config examples/corpus_equine_passport_eu_2015_262_v0_1.json \
  --output-dir dist/static-report \
  --use-llm

# lint export
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export \
  --export-dir dist/static-report

# inspect extraction jobs quickly
jq '{
  total: length,
  selected: ([.[] | select(.selected_for_extraction == true)] | length),
  skipped: ([.[] | select(.selected_for_extraction == false)] | length),
  repairable: ([.[] | select(.repairable == true)] | length)
}' dist/static-report/proposition_extraction_jobs.json

# inspect quality gate result
jq '{status, metrics, recommendations}' dist/static-report/run_quality_summary.json
```

## Relationship to quality and review

- `required_only` generally improves reviewability by reducing noisy fragment selection.
- Broad focus matching can improve recall but can add significant noise and review load.
- Lower proposition count is not automatically better if legally important provisions are missing.
- Human/legal review is still required before relying on extracted propositions.
- Promotion to guidance-ready status is a downstream governance step, not an extraction default.

## Known limitations

- Profile selection is a curation decision, not an objective completeness guarantee.
- Focus-term matching can overselect semantically adjacent but legally irrelevant text.
- Fragment locators must match canonical locator forms to be selected as required.
- Source discovery/corpus completeness and fragment extraction completeness are separate concerns.
