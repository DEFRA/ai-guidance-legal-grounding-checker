# LLM extraction: `local` and `frontier` modes

## What Law Proposition Extractor calls

Both `--extraction-mode local` and `--extraction-mode frontier` use the same **OpenAI-compatible LiteLLM proxy** (`LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL`, default `http://127.0.0.1:4000/v1`). Law Proposition Extractor does not talk to Ollama or Anthropic directly; it sends chat completions to LiteLLM **model aliases** defined in `config/litellm.yaml`.

| Mode | LiteLLM alias (env override) | Routed backend (default `litellm.yaml`) |
|------|------------------------------|----------------------------------------|
| `local` | `local_extract` (`LAW_PROPOSITION_EXTRACTOR_MODEL_LOCAL_EXTRACT`) | `ollama/qwen3:14b` @ `http://127.0.0.1:11434` |
| `frontier` | `frontier_extract` (`LAW_PROPOSITION_EXTRACTOR_MODEL_FRONTIER_EXTRACT`) | `anthropic/claude-sonnet-4-5-20250929` via `ANTHROPIC_API_KEY` |

Exported runs include **`MODEL.md`** with alias → provider model resolution from `config/litellm.yaml` (and `GET /model/info` when the proxy is up). New live LLM traces also record `response_model` from the completion payload when the proxy returns it.

**Proposition normalisation:** after extraction, the pipeline runs deterministic classification, jurisdiction, labelling, and relationship-key passes (recorded under `pipeline_case_inputs.proposition_normalisation` and in **MODEL.md**). See [Proposition classification](../architecture/proposition-classification.md).

`--use-llm` without `--extraction-mode` defaults extraction to **`local`** and divergence reasoning to **`frontier`**.

## Required services (local)

1. **Ollama** (or whatever `local_extract` points at) listening on port **11434**.
2. **LiteLLM proxy** on port **4000**: `just litellm`  
   - The recipe runs `env -u DATABASE_URL uvx litellm[proxy] --config config/litellm.yaml` so the proxy does not require a Postgres admin DB.
3. **Environment** (see `.env.example`):
   - `LAW_PROPOSITION_EXTRACTOR_LLM_BASE_URL=http://127.0.0.1:4000/v1`
   - `LAW_PROPOSITION_EXTRACTOR_LLM_API_KEY` (must match LiteLLM `master_key` / `LITELLM_MASTER_KEY`)

There is no separate Law Proposition Extractor “local profile” database. Corpus **profiles** (e.g. equine staged runs) are case JSON under `examples/`, not LLM routing profiles.

## Error: `400 No connected db.`

This message comes from the **LiteLLM proxy**, not from Law Proposition Extractor or `LAW_PROPOSITION_EXTRACTOR_DATABASE_URL` (Law Proposition Extractor’s SQLite ops store).

Typical cause: LiteLLM was started (or imported config) with **`DATABASE_URL` set** in the shell, so the proxy expects a reachable database for its admin/UI features, but no DB is connected.

**Fix:**

- Start the proxy via `just litellm` (unsets `DATABASE_URL`), or
- `unset DATABASE_URL` before starting LiteLLM manually, or
- Point `DATABASE_URL` at a real Postgres instance LiteLLM can reach.

Law Proposition Extractor surfaces the raw OpenAI SDK error as `model call or JSON parse failed: Error code: 400 - …` on each chunk; with `--extraction-fallback fail_closed` (default for `run-bundle --use-llm`) the run should not silently substitute heuristics.

## Preflight

Before processing fragments, the pipeline issues one minimal JSON chat completion against the selected alias (`local_extract` or `frontier_extract`). Failure stops the run early with the endpoint line (mode, profile, alias, base URL) and hints for common misconfiguration.

## Empty extraction diagnostics

Failed live LLM calls persist a safe `raw_model_output_excerpt` (up to 2k chars), `finish_reason`, `prompt_hash`, and a granular `failure_type` on each trace row:

| `failure_type` | Typical cause |
|----------------|---------------|
| `transport_empty_response` | Provider returned no message content |
| `parsed_empty_proposition_list` | Valid JSON with `"propositions": []` |
| `non_json_response` | Prose or unparseable JSON |
| `schema_valid_but_empty` | Valid JSON without extractable proposition objects (e.g. `{}`) |
| `post_filter_removed_all` | Model returned candidates that failed validation (e.g. evidence traceability) |

Inspect a prior export:

```bash
law-proposition-extractor-run-case inspect-extraction-jobs --export-dir runs/my-export --show-raw-failure-examples 5
```

Re-run one fragment against the configured endpoint (JSON diagnostics to stdout):

```bash
law-proposition-extractor-run-case debug-extract-fragment runs/my-run --source-id SRC --locator regulation:1 --extraction-mode local
```

For prompt refinement, write a full artifact bundle under a run folder (no full pipeline):

```bash
law-proposition-extractor-run-case extract-fragment \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --mode frontier \
  --output-dir runs/prompt-lab/diffuse-2018-reg-1 \
  --eval
```

(`--eval` requires a prompt-lab fixture with `expected_propositions`; default is `--no-eval`.)

Same via script:

```bash
uv run python scripts/extract_single_fragment.py \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/_workbench_dry_smoke.json \
  --mode dry \
  --output-dir runs/prompt-lab/diffuse-2018-reg-1-dry
```

Outputs: `fragment.txt`, `prompt.txt`, `raw_model_output.txt`, `parsed_extraction.json`, `propositions.raw.json`, `propositions.normalised.json`, `extraction_trace.json`, `review.md`, `MODEL.md`. Use `--mode dry` with `dry.raw_model_output` in the fixture to iterate on parsing/normalisation without calling the LLM.

Evaluate a run against fixture review targets:

```bash
law-proposition-extractor-run-case eval-extract-fragment \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --run-dir runs/prompt-lab/slurry-bad-diffuse-2018-reg-1
```

Writes `prompt_eval.json` and `PROMPT_EVAL.md` (pass/fail, per-expected matches, extra propositions, boilerplate/checkable checks).

## Run summary / quality

For `local` / `frontier` runs, summaries include live-call counters (`live_llm_calls_attempted`, `live_llm_calls_successful`, `live_llm_calls_failed`), cache reuse counters (`cached_llm_results_successful`, `cached_llm_results_failed`, `llm_results_reused_from_cache`), legacy aliases (`attempted_llm_calls` = live attempted; `successful_llm_calls` / `failed_llm_calls` = live only), `fallback_count`, `extraction_mode_requested`, `extraction_mode_effective`, and **`derived_cache_dir`**. Progress checkpoints, final timing, run summary, `manifest.json`, and inspect use the same trace aggregation. If every live and cached LLM outcome failed but heuristic fallback still produced rows (`live_llm_calls_successful + cached_llm_results_successful == 0` and `fallback_count > 0`), run quality is **`fail`** with: *No successful LLM extraction occurred.*

### Failed chunk derived cache

Per-chunk outcomes are cached under `{derived_cache_dir}/proposition_extraction_chunk/`. Chunk cache keys use **authority + `authority_source_id` + fragment locator + chunk body fingerprint** plus extraction config (model/prompt/strategy/pipeline) — not Law Discovery `lex-*` / `source_snapshot_id` — so re-intake with reminted source ids can still hit. Successful chunks are reused on re-run; **failed** chunks are **retried by default** when `--extraction-fallback fail_closed` (including `run-bundle --use-llm` default). To reuse cached failures without calling the model (zero-attempt runs), pass **`--ignore-failed-extraction-cache`**. To force retry explicitly: **`--retry-failed-extraction-cache`** (alias: `--retry-failed-llm`).

Identical fragment/snapshot bodies are also reused across runs via `{derived_cache_dir}/proposition_extraction_content_hash/` (same `content_hash` + extraction config), including EU/UK mirrors with different ASIDs.

**Key schema note:** older chunk files keyed on `source_snapshot_id` / `source_fragment_id` are unused after the ASID/content key change; clear or ignore them.

Clear only proposition extraction cache for a run (keeps narrative/classification caches):

```bash
DERIVED=/path/to/your/derived-cache   # same as run summary derived_cache_dir
rm -rf "$DERIVED/proposition_extraction" \
  "$DERIVED/proposition_extraction_chunk" \
  "$DERIVED/proposition_extraction_content_hash"
```

Or point the next run at a fresh directory: `--derived-cache-dir /path/to/fresh-derived`.
