# Audit Assembler

Audit Assembler is the final step in the pipeline. By the time data reaches her the
analysis is done; her job is to gather the upstream outputs and render them in
the shape the [content-audit frontend](../../ai-sdlc-content-audit) consumes.

She joins:

- **Proposition Matcher** — `results.json` (matched + classified guidance↔law propositions,
  each guidance entry carrying its native Guidance Proposition Extractor `id`).
- **Proposition Matcher's input pair** — `law.json` (Law Proposition Extractor's propositions). The guidance ids
  now come from Proposition Matcher's own output, so the input pair's `guidance.json` is no
  longer read.
- **Guidance Relevance Filter** — `output.json`, the source for the **audited pages** (`content_id`,
  page metadata + gov.uk analytics), per-page relevance (`meta_data.scores.slurry`),
  and the audited-corpus size (`total_pages_audited` = number of pages Guidance Relevance Filter was
  given). The pages Audit Assembler emits are those Proposition Matcher produced guidance for.
- **Reading age** — recomputed per audited page from the gov.uk content API
  (SMOG; ported from the standalone `reading-age` tool, cached on disk).
- **Seeds** — `categories.json` + `legislation.json` + `legislation-propositions.json`
  (the manually maintained law catalogue; re-keyed to native shape, never new data).

## Output shape (pipeline-native keys)

One file per entity, keyed by pipeline-native identifiers (no synthetic integer
ids):

| File | Key | Notes |
|---|---|---|
| `categories.json` | `id` (slug) | |
| `legislation.json` | `source_record_id` (`lex-…`) | |
| `legislation-propositions.json` | `id` (`prop:…` / `bcand:…`) | links to legislation by `source_record_id`; carries `fragment_locator` + `provision_url` (legislation.gov.uk deep-link when mappable) |
| `pages.json` | `content_id` (nullable) | audited pages; pages missing `content_id` are kept with `null` + a warning |
| `guidance-propositions.json` | `id` (`susan-…`) | native Guidance Proposition Extractor id; links to page by `content_id`; also carries `source_paragraphs` + `section_locator` (citation pin). `proposition_text` is the derived match text from Guidance Proposition Extractor/Proposition Matcher |
| `proposition-matches.json` | `id` (`m-…`) | **Compatibility** top-match projection: one Matcher-ranked top pair per guidance prop, plus synthesised law-side `GUIDANCE_MISSING` rows (`guidance_proposition_id: null`) and `NO_MATCH` rows for empty Matcher matches (`law_proposition_id: null`) |
| `guidance-proposition-match-summaries.json` | `guidance_proposition_id` | One proposition-level `assessment_status` + `coverage_result` per guidance prop (not pair rows); requires Matcher `match_processing` — empty matches alone is not `NO_CANDIDATES_FOUND` |
| `guidance-proposition-law-comparisons.json` | `id` (`m-…`) | All distinct **reportable** guidance–law pairs for rendering/audit (`GROUNDED`, `CONFLICTS`, `GUIDANCE_INCOMPLETE`, `GUIDANCE_BROADER`, `GUIDANCE_MISSING`). `UNGROUNDED` is intentionally absent (evaluated-but-rejected; remains in Matcher `results.json`). Ordered by guidance order, then Matcher rank. Only emitted for `COMPLETE` + `HAS_REPORTABLE_COMPARISON` |
| `page-relevance.json` | `content_id` | `relevance_score` from Guidance Relevance Filter |
| `pages-reading-age.json` | `content_id` | `word_count`, `reading_age` |
| `page-analytics.json` | `content_id` | `last_updated_date`, `view_count_period` |
| `subject-summary.json` | `category` | rollups; `total_pages_audited` = Guidance Relevance Filter corpus size |

There is **no** `page-aggregations.json` (correctness is not computable at this
stage) and **no** `legislation-aggregations.json` (the frontend derives coverage
itself). No silent fallbacks: anything that can't be derived is left null and
logged as a warning.

## Usage

```bash
uv sync

DATA=../../content-audit-data-assets/steps
uv run audit-assembler build \
  --proposition-matcher-run $DATA/proposition-matcher/runs/heron-verdict \
  --input-pair   $DATA/proposition-matcher/inputs/oats-byre-x-statute-badger \
  --relevance-filter-run    $DATA/guidance-relevance-filter/runs/lagoon-curlew/output.json \
  --seeds        $DATA/audit-assembler/seeds \
  --dest         ../../ai-sdlc-content-audit/src/server/services/audit/data \
  --reading-age-cache ../../reading-age/cache \
  --dry-run
```

When Matcher `law.json` was stripped of locators (common for `bcand:` candidate
exports), pass the full Law Proposition Extractor candidates file to join
`fragment_locator` by id and emit legislation.gov.uk `provision_url` deep-links:

```bash
uv run audit-assembler build \
  ... \
  --law-candidates $DATA/judit/runs/ssafo-nitrates-2-export/beatrice_law_candidates.json
```

Drop `--dry-run` to write the files. The reading-age cache is keyed the same way
as the standalone tool (`sha1(content-api-url)`), so pointing `--reading-age-cache`
at the existing `reading-age/cache` reuses already-fetched pages.

`build` also writes `pairs.csv` into `--dest` (skipped with a warning when match
summaries are missing). The audit frontend serves that file as a subject download.

## Export pairs CSV

Post-process assembled presentation data into a denormalized spreadsheet
(JSON remains the source of truth — this is not a parallel output type).
`build` already emits `pairs.csv` for a flat dest; use this command for packed
run envelopes (the frontend copies `pairs.csv` next to `output.json`):

```bash
uv run audit-assembler export-csv \
  --input  ../../content-audit-data-assets/steps/esther/runs/ssafo-nitrates/output.json
```

`--out` defaults to `pairs.csv` next to `--input`. `--input` accepts an envelope
`output.json` or a flat assembled directory (same files `build` writes to `--dest`).

**Grain**

- One row per reportable pair in `guidance-proposition-law-comparisons.json`
- Plus one stub row (law columns empty) for every guidance proposition with
  zero reportable pairs — including `NO_CANDIDATES_FOUND`,
  `ONLY_UNGROUNDED_CANDIDATES`, and processing states (`NOT_CHECKED` /
  `PARTIAL` / `FAILED`)
- Requires non-empty `guidance-proposition-match-summaries.json` (rebuild
  older runs through Audit Assembler first)
- Does not emit law-side synthetic `GUIDANCE_MISSING` rows

Stub rows still carry page/guidance text plus `assessment_status` /
`coverage_result` so you can filter why there is no law side.

## Validate assembled guidance–law comparison contract

After a build (or against any assembled flat data directory):

```bash
uv run audit-assembler validate-guidance-comparison-contract \
  ../../ai-sdlc-content-audit/src/server/services/audit/data
```

Fails with actionable messages naming the guidance proposition id, broken
invariant, and expected vs actual counts/states.

## Matcher `match_processing` boundary

Assembler **never invents** historic processing state. Missing
`match_processing` → proposition-level `NOT_CHECKED` (legacy path). Valid native
or approved reconstructed rows (provenance
`origin=historic_backfill` +
`policy_version=historic_match_processing_backfill_v1`) are consumed as-is.
Purported historic backfills with missing/invalid provenance are rejected at
build time. Reconstruction itself lives in Proposition Matcher
(`backfill-match-processing`); see that package’s
`docs/historic-match-processing-backfill.md`.

## Tests

```bash
uv run pytest        # pure transform + reading-age scoring, no network
```
