# Equine passport staged runs

## Purpose

`equine_passport_identification_v0_1` is the umbrella profile for equine passport identification. It is large and better suited to batch-oriented execution. For interactive frontier extraction and review, run the staged profiles below.

## Staged profiles

### `equine_passport_eu_2015_262_v0_1`

- Corpus config: `examples/corpus_equine_passport_eu_2015_262_v0_1.json`
- Case: `examples/equine_passport_eu_2015_262_case.json`
- Purpose: EU 2015/262 equine passport baseline

### `equine_passport_england_ukwide_v0_1`

- Corpus config: `examples/corpus_equine_passport_england_ukwide_v0_1.json`
- Case: `examples/equine_passport_england_ukwide_case.json`
- Purpose: England + UK-wide retained/EU Exit equine identification layer

### `equine_passport_devolved_v0_1`

- Corpus config: `examples/corpus_equine_passport_devolved_v0_1.json`
- Case: `examples/equine_passport_devolved_case.json`
- Purpose: Wales / Scotland / Northern Ireland equine identification layer

## Estimate commands

### Estimate `equine_passport_eu_2015_262_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline estimate-corpus-run \
  examples/equine_source_universe.json \
  --profile equine_passport_eu_2015_262_v0_1 \
  --fetch
```

### Estimate `equine_passport_england_ukwide_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline estimate-corpus-run \
  examples/equine_source_universe.json \
  --profile equine_passport_england_ukwide_v0_1 \
  --fetch
```

### Estimate `equine_passport_devolved_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline estimate-corpus-run \
  examples/equine_source_universe.json \
  --profile equine_passport_devolved_v0_1 \
  --fetch
```

## Build commands

Before running builds:

- Ensure LiteLLM is running.
- Ensure `ANTHROPIC_API_KEY` has available credits.
- Prefer a persistent derived cache if one is available.
- Run `lint-export` after each build.

### Build `equine_passport_eu_2015_262_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline build-equine-corpus \
  --corpus-config examples/corpus_equine_passport_eu_2015_262_v0_1.json \
  --output-dir dist/static-report \
  --use-llm
```

### Build `equine_passport_england_ukwide_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline build-equine-corpus \
  --corpus-config examples/corpus_equine_passport_england_ukwide_v0_1.json \
  --output-dir dist/static-report \
  --use-llm
```

### Build `equine_passport_devolved_v0_1`

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline build-equine-corpus \
  --corpus-config examples/corpus_equine_passport_devolved_v0_1.json \
  --output-dir dist/static-report \
  --use-llm
```

## Quality checks

After each run:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export \
  --export-dir dist/static-report
```

Then inspect:

- `/propositions?scope=equine`
- Run quality summary
- Repair banner
- Fallback count
- Low-confidence traces
- Context-window risks
- `guidance-ready` remains `0` until reviewed

## Batch note

The umbrella profile is appropriate for batch mode once the full batch lifecycle is integrated. For interactive development and review, staged profiles are the better default.

## Warnings

- Do not claim complete equine passport law coverage from one staged profile.
- Do not run the full 21-source universe interactively unless you are intentionally testing scale.
- If repairable extraction failures appear, restore provider credits and repair failed chunks rather than rerunning everything.
