# Proposition Matcher

The matching stage of the Guidance Relevance Filter → Guidance Proposition Extractor → Proposition Matcher pipeline. It takes Guidance Proposition Extractor's
guidance propositions and Law Proposition Extractor law (raw propositions **or** guidance-matching
candidates), retrieves the closest law units by semantic similarity, then
**group-reranks** each guidance proposition — a single LLM call sees all of its
surviving law candidates at once and labels each one — to find where guidance
conflicts with, matches, or omits the law.

This is a **headless pipeline** (JSON in, JSON out) run via `proposition-matcher run`. No
server, no UI.

## What it does

1. **Retrieve** — embeds guidance and law units and selects a small survivor set of the closest law candidates per guidance proposition (cosine threshold + an adaptive `score_gap` window, capped at `top_k`)
2. **Group-rerank** — a single LLM call per guidance proposition judges every surviving candidate together and labels each: `GROUNDED`, `UNGROUNDED`, `CONFLICTS`, `GUIDANCE_INCOMPLETE`, `GUIDANCE_BROADER`, or `GUIDANCE_MISSING`. A proposition with no candidate above the threshold costs no LLM call.
3. **Summarise** — generates a concise compliance summary for each guidance proposition that has at least one non-`UNGROUNDED` match
4. **Output** — writes `results.json` + `results.csv` (one row per guidance/law match) plus `match_summaries.json`, `metrics.json`, and a human-readable `MODEL.md`. Each `results.json` guidance row keeps `content_id`, `source_paragraphs`, `section_locator`, and `law_source` for provenance; guidance matching still embeds the derived `proposition_text` only. Pair-level `relationship` stays on each match; each guidance row also carries `match_processing` (retrieval/classification evidence) and `match_summary` (proposition-level assessment/coverage). Empty `matches` alone does not mean “no candidates”.

## Architecture

A single package (`src/proposition-matcher/`), like Guidance Relevance Filter and Guidance Proposition Extractor. Run via `./run.sh` or
`uv run proposition-matcher`.

```
src/proposition-matcher/
  cli.py                proposition-matcher run
  domain/               Proposition (law) model + SourceRecord models
  guidance/             GuidanceProposition model + Guidance Proposition Extractor-output mapping
  matching/             Embeddings + cosine retrieval, group-rerank matcher, prompts
  pipeline/             batch_match + law_loading (dual Law Proposition Extractor inputs) + Guidance Proposition Extractor mapping
```

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- An `ANTHROPIC_API_KEY` (the group-rerank + summarise calls go to the Anthropic Message Batches API)
- [Ollama](https://ollama.com/) with `nomic-embed-text:v1.5` pulled (`ollama pull nomic-embed-text:v1.5`) for local embeddings

## Setup

```bash
cp .env.example .env        # set ANTHROPIC_API_KEY
uv sync
```

## Configuration

The matcher's behaviour (retrieval geometry, prompt, models) is fixed in code —
it is the configuration that won the benchmark ladder, not a set of runtime
knobs. Only infra is environment-driven:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | group-rerank + summarise calls |
| `EMBED_BASE_URL` | `http://127.0.0.1:11434/v1` | local embedding endpoint (Ollama) |
| `EMBED_MODEL` | `nomic-embed-text:v1.5` | embedding model |

## Batch matching (Guidance Proposition Extractor -> Proposition Matcher)

One opinionated command runs the full group-rerank match via the Anthropic
Message Batches API (50% cost), one grouped request per guidance proposition:

```bash
# Preferred when available: Law Proposition Extractor's filtered matching queue
./run.sh run \
  --guidance path/to/guidance-proposition-extractor-output.json \
  --law path/to/proposition_matcher_law_candidates.json \
  --out runs/my-run/

# Legacy / explicit: raw Law Proposition Extractor propositions
./run.sh run \
  --guidance path/to/guidance-proposition-extractor-output.json \
  --law path/to/law-proposition-extractor-propositions.json \
  --law-source propositions \
  --out runs/my-run/
```

(`./run.sh run …` is shorthand for `uv run proposition-matcher run …`.) Outputs
`results.json`, `results.csv`, `metrics.json`, and a human-readable `MODEL.md`.

Both inputs are consumed **verbatim** — Proposition Matcher does not refetch or re-extract:
`--guidance` is a **Guidance Proposition Extractor run's `output.json`** (flattened to `GuidanceProposition`
by `pipeline/mapping.py`), and `--law` is either:

- **`proposition_matcher_law_candidates.json`** (recommended) — filtered `guidance_matching_candidate`
  queue from Law Proposition Extractor's effective-law export. Retrieval embeds `matching_text`; the
  LLM sees `statement_text`.
- **`propositions.json`** — Law Proposition Extractor `Proposition` export. Embeds/displays
  `proposition_text`.

`--law-source` defaults to `auto` (sniff JSON shape). Pass `propositions` or
`candidates` to force a mode; a mismatch exits with an error. A reshaped
`legislation-propositions.json` (e.g. Audit Assembler's seeds) is **not** a valid `--law`
input; it won't pass `Proposition` validation.

The retrieval geometry (`top_k 15`, `threshold 0.65`, `score_gap 0.04`), the
prompt, and the model are fixed in code — the configuration that won the
benchmark ladder (see `benchmark_generators/proposition-matcher/versions/`).

Use `--dry-run` to embed + retrieve and count requests without any API spend.
Nothing is cached between runs — each run embeds, retrieves, and group-reranks
afresh.

## Historic `match_processing` backfill

Pre-`match_processing` Matcher runs cannot unlock the guidance-comparison
contract safely from empty `matches[]` alone. The official fail-closed policy is
`historic_match_processing_backfill_v1` — see
[docs/historic-match-processing-backfill.md](docs/historic-match-processing-backfill.md).

```bash
# Analyse eligibility (writes nothing)
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-run \
  --check

# Write a derived run only when every proposition is reconstructable
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-run \
  --dest path/to/derived-run
```

`candidate_count` means **retrieval survivors**, never `len(matches)`. Ambiguous
runs stay on the legacy frontend path until Matcher is re-run or richer
evidence (e.g. `survivors.json`) is available. The acceptance copy under
`runs/acceptance/ssafo-nitrates-current/` is acceptance-only and is not this
policy.

## Validate a native Matcher run

After `proposition-matcher run`, gate adjudication readiness:

```bash
uv run proposition-matcher validate-run \
  --run path/to/matcher-run \
  --guidance path/to/guidance-proposition-extractor-output.json \
  --law path/to/proposition_matcher_law_candidates.json \
  --law-source candidates \
  --write-json path/to/matcher-run/native-run-validation.json
```

This recomputes local retrieval survivors and checks that every guidance row has
schema-valid native `match_processing` with `candidate_count` equal to the
live survivor count.

## Reconcile a Matcher rerun

Compare a new native run to historic Beatrice, Anna, and an acceptance-only copy:

```bash
uv run proposition-matcher reconcile-rerun \
  --new-run path/to/new-matcher-run \
  --beatrice path/to/historic-beatrice-run \
  --anna path/to/anna-run \
  --acceptance path/to/acceptance-derived-run \
  --validation-json path/to/new-matcher-run/native-run-validation.json
```

Writes `MATCHER-RERUN-REPORT.md` and `matcher-rerun-reconciliation.json` under
the new run. Does not apply adjudications.
