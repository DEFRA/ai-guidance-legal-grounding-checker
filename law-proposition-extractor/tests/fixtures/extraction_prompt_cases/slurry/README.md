# Slurry extraction prompt-lab fixtures

These JSON files support **single-fragment legal proposition extraction** prompt refinement (`law-proposition-extractor-run-case extract-fragment` / `scripts/extract_single_fragment.py`). They are drawn from the principal slurry corpus export (`runs/slurry-gb-principal-5-frontier-export`) and are **not** a complete legal test suite.

## Purpose

- Iterate on prompts, schema, and few-shots **without** a full pipeline run.
- Compare model output against **review targets** in each fixture (`expected_propositions`, `expected_challenges`).
- Cover **good**, **bad**, and **ugly** fragment shapes seen in production and in `normalised_proposition_review.json`.

## Fixture shape

Each file includes:

| Field | Role |
| --- | --- |
| `case_id` | Stable id (matches filename stem). |
| `label` | Human category, e.g. `GOOD — simple prohibition`. |
| `source_title` / `source_record_id` / `source_jurisdiction` | Provenance from the export. |
| `fragment_locator` / `fragment_text` | Exact chunk sent to extraction. |
| `why_this_case` | Why this fragment is in the lab set. |
| `expected_challenges` | Parsing/normalisation risks to watch for. |
| `expected_propositions` | **Review targets** after extraction + normalisation (not legal advice). |

## Initial set (11)

| File | Tier | Eval mode | Focus |
| --- | --- | --- | --- |
| `slurry-good-simple-prohibition-spread-buffer.json` | GOOD | targeted | Clear `must not spread` buffer (NPP 2015 reg 17). |
| `slurry-good-simple-obligation-170kg-n.json` | GOOD | targeted | Occupier `must ensure` + 170 kg N limit (reg 7). |
| `slurry-good-definition-slurry-sssaho-2010.json` | GOOD | targeted | `slurry` definition block (SSSAHO 2010 reg 2). |
| `slurry-bad-diffuse-2018-reg-1-boilerplate.json` | BAD | exhaustive | Citation / commencement / extent / application (Diffuse 2018 reg 1). |
| `slurry-bad-npp-reg-2-definitions.json` | BAD | minimum | NPP reg 2 interpretation definitions + statutory quote JSON repair (slurry, organic manure, agricultural, spreading). |
| `slurry-bad-over-compressed-crop-nitrogen-table.json` | BAD | minimum | Table + long-label risk (NPP reg 12). |
| `slurry-bad-unless-except-organic-manure-250kg.json` | BAD | minimum | Conditions, exceptions, permissions (NPP reg 8). |
| `slurry-ugly-schedule-livestock-manure-table.json` | UGLY | table_rows | Schedule 1 numeric livestock / N / P table. |
| `slurry-ugly-transitional-nvz-wales-reg-2.json` | UGLY | minimum | Staggered transitional dates (Wales reg 2). |
| `slurry-ugly-cross-reference-derogation-directive.json` | UGLY | minimum | Directive/Annex derogation cross-refs (reg 36). |
| `slurry-ugly-appeal-nvz-designation-reg-6.json` | UGLY | minimum | Appeal grounds and Tribunal (reg 6). |

## Usage

### Single fixture

```fish
uv run law-proposition-extractor-run-case extract-fragment \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --mode local \
  --output-dir runs/prompt-lab/slurry-bad-diffuse-2018-reg-1

# Optional: score against expected_propositions in the same run
uv run law-proposition-extractor-run-case extract-fragment \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --mode local \
  --output-dir runs/prompt-lab/slurry-bad-diffuse-2018-reg-1 \
  --eval
```

Use `--mode dry` only with fixtures that include a `dry` block (see `_workbench_dry_smoke.json` for unit tests).

### Batch (all fixtures)

Run every fixture in a directory, evaluate by default, and write an aggregate summary:

```fish
uv run law-proposition-extractor-run-case extract-fragment-batch \
  --fixture-dir tests/fixtures/extraction_prompt_cases/slurry \
  --mode frontier \
  --output-root runs/prompt-lab/baseline-frontier
```

Equivalent script:

```fish
uv run python scripts/extract_fragment_batch.py \
  --fixture-dir tests/fixtures/extraction_prompt_cases/slurry \
  --mode frontier \
  --output-root runs/prompt-lab/baseline-frontier
```

Discovery skips helper fixtures (`_*.json`) and `eval_runs/**`. Useful options:

| Flag | Purpose |
| --- | --- |
| `--limit N` | Run at most N fixtures |
| `--fixture-glob PATTERN` | e.g. `slurry-good-*.json` |
| `--fixture PATH` | Repeatable; run specific fixtures (can combine with `--fixture-dir`) |
| `--no-eval` | Extraction only |
| `--no-overwrite` | Skip fixtures whose output dir already exists |
| `--fail-fast` | Stop on first fail/error |

Batch outputs under `--output-root`:

- `PROMPT_LAB_SUMMARY.md` — human-readable table + failure themes + verdict
- `prompt_lab_summary.json` — machine-readable rows
- `<fixture-stem>/` — same artifacts as single `extract-fragment` (plus `prompt_eval.*` when eval is on)

### Interpreting the batch summary

Each row includes: fixture, tier (`good`/`bad`/`ugly`), evaluation mode, status (`pass`/`warn`/`fail`/`error`/`skipped`), matched expected count, extras, and failure themes.

**Verdict guide:**

| Verdict | Meaning |
| --- | --- |
| `all_pass` | Every runnable fixture passed eval |
| `pass_with_warnings` | Passed with extras, compression warnings, or skipped dry fixtures |
| `fixture_policy_review_needed` | Most fails matched all gold rows but failed on exhaustive count/extras — review `evaluation.mode` |
| `failures_require_fixture_or_eval_update` | Count/extras/gold-standard mismatch — update fixture or eval mode |
| `failures_suggest_prompt_change` | Unmatched expected rows from omissions, weak subject/action, bad legal structure |
| `failures_suggest_infrastructure_issue` | JSON parse, extraction transport, table evidence validation |

**When to change what:**

- **Prompt** — repeated `failures_suggest_prompt_change` across `good`/`bad` tiers; missing substantive rows the fixture expects.
- **Fixture / evaluator** — `targeted`/`minimum`/`table_rows` extras allowed but gold rows wrong; update `expected_propositions` or `evaluation.mode`.
- **Infrastructure** — empty parses, evidence salvage, workbench errors with good raw model output.

## Evaluation

After a workbench run, score output against `expected_propositions`:

```fish
uv run python scripts/eval_single_fragment_extraction.py \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --run-dir runs/prompt-lab/slurry-bad-diffuse-2018-reg-1
```

Or:

```fish
law-proposition-extractor-run-case eval-extract-fragment \
  --fixture tests/fixtures/extraction_prompt_cases/slurry/slurry-bad-diffuse-2018-reg-1-boilerplate.json \
  --run-dir runs/prompt-lab/slurry-bad-diffuse-2018-reg-1
```

Writes `prompt_eval.json` and `PROMPT_EVAL.md` into the run directory. Optional fixture `evaluation` block:

- `mode` — `targeted` | `minimum` | `exhaustive` | `table_rows` (see Prompt 35)
- `strict_proposition_count` — actual count must equal expected count (exhaustive default)
- `allow_extra_actual` — whether extra propositions fail eval
- `expected_checkable_count` — Proposition Matcher-checkable rows (e.g. `0` for reg 1 boilerplate)
- `max_extra_actual` — optional cap on allowed extras

Saved evaluation samples (no LLM) live under `eval_runs/` for unit tests.

## Important limitations

- **`expected_propositions` are review targets**, not authoritative legal conclusions or client advice.
- Fixtures intentionally **do not** cover the full slurry instrument set, Wales/Scotland parity, or all annexes.
- Fragment text is a **snapshot** from one export; legislation may have been amended since capture.

## Internal test fixture

`_workbench_dry_smoke.json` uses the legacy `topic` / `cluster` / `source` / `dry` shape for CI dry-mode tests only; prefer the prompt-lab schema above for new cases.
