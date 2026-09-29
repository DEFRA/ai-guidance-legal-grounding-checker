# Guidance Relevance Filter

Guidance Relevance Filter is the opinionated filter that Guidance Discovery is not. Given the full Defra
guidance corpus and a category, she narrows it to the pages that genuinely
belong to that topic. Where Guidance Discovery asks "is this a Defra guidance page?",
Guidance Relevance Filter asks "is this a Defra guidance page about *this* category?".

This package is Guidance Relevance Filter's **production shape**: one classifier, one category,
standalone — nothing to run beyond this directory and the Anthropic API.

## What it bakes in

Two passes on Anthropic: a recall-maximising classifier in front of a precision
adjudicator. Default transport is the Message Batches API (0.5×). Pass `--sync`
to use the standard Messages API instead (full price, faster).

**Pass 1 — recall (cheap-gate routing + Claude Haiku).**

- **Word-search routing (default).** A page reaches the LLM only if its title or
  body hits the curated inclusion lexicon (`src/guidance-relevance-filter/data/lexicon.json`),
  NLTK Porter-stemmed. On a sparse corpus this prunes most pages before any
  API call. Pages with no hit are recorded `{category}: false` **without** an LLM
  call (`lexicon_miss`) — the absence of an inclusion hit *is* the exclusion mechanism.
- **Cosine routing (`--router cosine`).** Alternative cheap gate: nomic-embed-text
  cosine of the title + body against the category query (`embedding_query` if set,
  else `description`). Below `--cosine-threshold` (default 0.2) is `cosine_miss`.
  Requires `uv sync --extra cosine`. `--score-only` runs this gate (or wordsearch)
  and writes the funnel **without** calling Anthropic, for threshold tuning.
  First cosine run on a corpus writes page vectors to
  `<input-dir>/embed_index/<sha>__<model>.pkl`; later runs (any category /
  threshold) reuse them and only encode the query.
- **`claude-haiku-4-5-20251001`** via the batch API (or `--sync`) for the pages that do hit.
  Homonym gate: TRUE if any hit is in the intended sense of the category (a
  single table cell counts); FALSE only for a different sense of the word.
  Incidental-but-right-sense mentions are pass 2's job. Prompted with the
  category description **minus** its *Exclusion Criteria* section, and with
  **windows around lexicon hits** rather than the full body (so a capital-item
  row in a CS manual is visible). Cosine routing still sends the full body.
- **Oversized-page rescue.** A page too large for the batch is retried once on
  the immediate Messages API using the same hit windows, truncated only if that
  payload still exceeds the word cap; the trim is stamped into the reason,
  never silent.

**Pass 2 — precision (Claude Sonnet adjudication).**

- Every page pass 1 labelled `{category}: true` is re-read by `claude-sonnet-4-6`
  (same transport as pass 1) with the *Exclusion Criteria* **re-introduced**
  (`categories.json`'s `exclusion_criteria`). It drops the false positives pass 1
  over-includes — homonyms, wrong-domain mentions, and pages that merely name the
  topic in passing.
- Optional **`adjudication_hints`** in `categories.json` (`keep` / `drop` bullet
  lists) tune pass 2 for category-specific borderline cases without hardcoding
  prompts in Python.
- **It can only turn a TRUE into a FALSE**, so the exclusion criteria cost pass 1
  no recall: the pages the word-search never routed are untouched. The
  prompt is tuned to the recall-priority operating point — it removes only
  unambiguous out-of-scope noise and keeps anything with real audit value for
  the category.

**No silent fallbacks.** Skipped pages carry an explicit "excluded by
word-search" reason. A pass-1 routed page that can't be classified even after
rescue raises `ClassificationIncomplete`. Auth, billing, and unknown-model
errors abort with the Anthropic error instead of looking like 30 independent
page misses. A pass-2 verdict that won't parse leaves
the page as pass 1 labelled it (kept) and is counted `unadjudicated` — never
quietly dropped.

## Usage

```bash
uv sync
export ANTHROPIC_API_KEY=sk-...

# Narrow a page corpus (Guidance Discovery's output shape) down to on-topic pages
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/

# Crash / sleep / killed process: re-run the same command against the same
# output dir. If `checkpoint.json` is still there, the run reattaches to the
# existing Anthropic batch instead of submitting a new one. `--fresh` abandons
# the checkpoint (and does NOT cancel the old batch on Anthropic).

# Use alternate category data (wordsearch still needs a lexicon)
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/ \
  --categories path/to/categories.json \
  --lexicon path/to/lexicon.json

# Abort before Anthropic if the cheap gate would send too many pages
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/ \
  --max-routed 600

# Same prompts, standard Messages API (full price, faster than batch)
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/ \
  --sync --concurrency 10

# Cosine gate instead of the inclusion lexicon (needs: uv sync --extra cosine)
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/ \
  --router cosine --score-only
uv run guidance-relevance-filter run path/to/pages.json path/to/output_dir/ \
  --router cosine --cosine-threshold 0.25

# Annotate a gold URL list with where each URL died (or was kept)
uv run guidance-relevance-filter explain urls.csv path/to/output_dir/ -o annotated.csv
uv run guidance-relevance-filter explain urls.csv path/to/output_dir/funnel.json \
  --url-column "Original URL"

# Same join in a browser (upload CSV + output.json / funnel.json)
uv sync --group web
uv run guidance-relevance-filter serve
```

`pages.json` is a list of `{url, content_id, meta_data: {title, body_text, ...}}`
objects — pages must carry `meta_data.body_text` (Guidance Relevance Filter classifies the body, she
does not fetch it). For a sharded fetch, pass `--shard-name <name>` to stamp
per-row `source_shard` provenance.

### Configuration

- **`ANTHROPIC_API_KEY`** (required) — the routed pages go to the Anthropic API.
  It can be exported or placed in a `.env` file (loaded automatically).
- **`LLM_MODEL_ANTHROPIC`** (optional) — overrides the pass-1 model
  (`claude-haiku-4-5-20251001`); `--model` on the command line wins over both.
- **`GUIDANCE_RELEVANCE_FILTER_ADJUDICATOR_MODEL`** (optional) — overrides the pass-2 model
  (`claude-sonnet-4-6`); `--adjudicator-model` on the command line wins over both.
- **`--categories` / `--lexicon`** (optional) — override the packaged category
  definition and/or inclusion lexicon. Wordsearch requires a lexicon (packaged
  default, or `--lexicon`). Cosine does not; `--categories` can be passed alone.
- **`--router wordsearch|cosine`** — cheap gate. Default `wordsearch`. Cosine
  needs `uv sync --extra cosine`.
- **`--cosine-threshold` / `--embed-model`** — cosine-router only (defaults
  `0.2` / `nomic-ai/nomic-embed-text-v1.5`).
- **`--score-only`** — run the cheap gate, write `output.json` / `funnel.json` /
  metrics, skip both Anthropic passes.
- **`--max-routed N`** — after the cheap gate, abort (exit 1) if more than `N`
  pages would go to Anthropic. Still writes `funnel.json` / `metrics.json`
  (`capped: true`). Ignored with `--score-only` and when resuming a pass-1 run.
- **`--sync`** — standard Messages API instead of Message Batches (full price,
  faster). Default is batch (0.5×). `--concurrency` (default 10) is the parallel
  call cap; ignored in batch mode. A leftover checkpoint from the other mode
  is `ResumeIncompatible` (use `--fresh` or a new output dir).
- **`--stem-index PATH`** — directory or `.sqlite` for the Porter-stem inverted
  index, keyed by sha256 of the input JSON. Default: `<input-dir>/stem_index/`.
  First wordsearch on a corpus writes it; later runs (and the operator UI)
  reuse it. Pass a `.sqlite` from another file (full snapshot vs a slice) to
  match by URL. Cosine routing ignores this. Leftover `.pkl` files are unused.
- **`--embed-index PATH`** — directory or `.pkl` for the page-embedding cache,
  keyed by sha256 of the input JSON + `--embed-model`. Default:
  `<input-dir>/embed_index/`. First cosine run writes it; later cosine runs
  reuse the vectors. Wordsearch ignores this. Changing the category query or
  `--cosine-threshold` does **not** invalidate it.
- **`--fresh`** — ignore `checkpoint.json` and submit new batches. Does not
  cancel anything already queued on Anthropic.

While a run is in flight, `output_dir/checkpoint.json` holds the Anthropic batch
ids (batch mode) or per-reply texts (sync) plus a fingerprint of the
input/category/models/llm mode. Re-running the same command against that
directory reattaches (poll retries disconnects forever, so a sleep/wake of the
same process also survives). The file is deleted once
`output.json` / `funnel.json` / `MODEL.md` / `metrics.json` are written.

`output_dir/` ends up containing:

- `output.json` — the input pages with the **final** `meta_data.labels.{category}`
  (bool, post-pass-2), plus `meta_data.scores.{category}` (pass-1 signal),
  `meta_data.reasons.{category}` (the deciding pass's reason),
  `meta_data.funnel` (per-page drop stage + both passes' reasons), and
  `selection_strategy_body` / `selected_categories_body` / `selection_meta_body`.
  `body_text` is dropped (it lives upstream). This is the output shape that
  downstream steps (e.g. Guidance Proposition Extractor) consume. Pages with empty/missing `body_text`
  are **kept** in `output.json` with `labels=false` and an explicit
  `skipped: empty body_text` / `skipped: missing body_text` reason (not silently dropped).
- `adjudication.json` — the pass-1-vs-pass-2 audit trail, one record per pass-1
  positive: `stage`, `pass1_score`, `pass1_reason`, `pass2_keep`, `exclusion_hit`,
  `pass2_reason`. Kept off the pipeline output path.
- `funnel.json` — drop journal. Counts for every funnel step; a URL list
  (url, title, document_type, plus LLM reasons / exclusion tag / fetch_error
  where they apply) for **every** stage: `missing_body`, `empty_body`,
  `lexicon_miss`, `cosine_miss`, `pass1_false`, `pass2_drop`, `pass2_keep`,
  `pass2_unadjudicated`. `routing_miss` in `counts` is `lexicon_miss + cosine_miss`.
  Look up one URL with
  `jq --arg u "$URL" '.. | objects | select(.url == $u)' funnel.json`.
- `MODEL.md` — models, started_at, process elapsed, the input→lexicon→pass-1→pass-2 **funnel** (counts plus what each number means, including Anthropic batch ids), pass-2 exclusion-tag breakdown, jq snippets, and a per-pass **cost** summary.
- `metrics.json` — machine-readable run record. `llm_mode` is `batch` or `sync`. `elapsed_seconds` is this CLI process (wordsearch + both LLM passes). `funnel` is the same breakdown with a `meaning` on every count (including `missing_body`, `pass1_false` and `pass2_dropped_by_exclusion_hit`); `pass1`/`pass2` carry token totals, `batch_meta` (Anthropic batch id or sync elapsed/concurrency, submitted vs collected, `request_counts`, elapsed seconds), `resumed` (whether this process reattached to a checkpointed batch or stored replies), and `cost_usd` (pass 1 Haiku, pass 2 Sonnet; batch-discounted unless `--sync`). An overridden model that isn't priced records `cost_usd: null` (tokens still recorded) rather than a guessed figure.

`explain` / `serve` take a URL CSV plus that run dir (or `output.json` / `funnel.json` directly). Default URL column is `url`; if that header is missing it falls through to `Original URL`, then `clened-urls`. `--url-column` overrides (hard error if absent). Every input row is preserved; `funnel_stage` and `funnel_reason` are appended. A URL that never appeared in the run is `not_in_corpus`.

Inspect a finished run interactively (stage counts, drop reasons, per-URL lookup):

```bash
cd guidance-relevance-filter
uv sync --group notebook
uv run jupyter notebook inspect_funnel.ipynb
```

- `checkpoint.json` — **ephemeral**. Present only while a run is in flight so a
  killed process can reattach. Not part of the downstream contract; gone when
  the run finishes.

## Category data

The packaged defaults live in `src/guidance-relevance-filter/data/`:

- `categories.json` — one category object: `name`, `description`,
  `exclusion_criteria`, optional `adjudication_hints` (`keep` / `drop` lists),
  and optional `embedding_query` (short text used as the cosine search query;
  falls back to `description`).
- `lexicon.json` — inclusion terms keyed by category name (wordsearch router).

To run a different topic, swap both files or pass `--categories` and `--lexicon`.
Guidance Proposition Extractor's `prepare --category <name>` must match the `name` field in your category
data.

## Tests

```bash
uv run pytest
```

The tests cover word-search routing, pass-1 response parsing (including
truncated-JSON repair), bulk labelling, oversized-page rescue, pass-2
adjudication (drop / keep / keep-on-unparseable / truncation-stamping), custom
category paths, the no-silent-fallback contract, the per-stage funnel
journal (including missing-body vs empty-body), and the sync adapter's
resume-from-replies path. They run **offline** with no API key: the skip path
never calls the API, and the LLM paths use a `FakeCompletions` double.

## Validation

Guidance Relevance Filter only writes runs. Scoring a run's labels against a labelled benchmark
(recall over on-topic pages / precision / per-page agreement) is a separate
validation step, maintained outside this pipeline repo.

## What this isn't

- Not multi-provider. Single API, single model.
- Not multi-category. The package bakes in one category + lexicon at a time; a new
  category is a new pair of data files (`categories.json` + `lexicon.json`).
- Not a fetcher. Pages must already carry `body_text`.
- Not wired into any orchestrator. Guidance Relevance Filter is standalone — wiring is a later,
  separate decision.
- Not a workspace member of any monorepo. Standalone `pyproject.toml`.
