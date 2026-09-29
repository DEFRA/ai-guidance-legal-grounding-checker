# Guidance Proposition Extractor

Guidance Proposition Extractor reads the full body of a GOV.UK guidance page and decomposes it into
atomic propositions — single, self-contained statements of what the guidance
asserts.

Each proposition carries contextual metadata fields that keep it useful
when lifted out of its surrounding page:

| Field | Purpose |
|---|---|
| `proposition_text` | **Derived** rewrite for matching/readability — atomic and self-contained, not a verbatim quote of the page. |
| `subject_area` | The broad domain (e.g. "nitrate vulnerable zones"). |
| `instrument` | The specific named licence, permit, regulation, scheme, form, or online service the obligation arises under. |
| `actor` | The role on which the obligation falls (e.g. "licence holder"). |
| `source_paragraphs` | **Citation pin** — LLM-claimed verbatim paragraphs or list-items the proposition was drawn from. |
| `section_locators` | Post-hoc H2 section ids matched from `source_paragraphs` against the fetched page (not LLM-emitted). |
| `regulatory_kind` | A controlled-vocabulary tag for the KIND of regulatory artefact: `statutory_obligation`, `permit_requirement`, `grant_condition`, `code_of_practice`, `procedural_step`, `factual_statement`, or `definition`. |
| `derives_from` | A list of verbatim citations to underlying legislation when the page names a legal basis. Empty when the page does not cite — Guidance Proposition Extractor never guesses. |

## What it bakes in

One candidate configuration, proven over pairwise human comparison:

- Anthropic, `claude-sonnet-4-6`
- Structured adapter (page sections prefixed with their H2 locator)
- A single prompt: the "tightened + metadata" prompt
- Contextual metadata fields per proposition: `subject_area`, `instrument`,
  `actor`, `source_paragraphs`, `regulatory_kind`, `derives_from`, plus
  post-hoc `section_locators` (see the field table above)
- Soft metric `source_paragraph_verbatim_misses` in `metrics.json` counts
  props whose `source_paragraphs` are not a whitespace-collapsed substring of
  the page (does not fail the run)
- **No fallback.** JSON parse failures and API errors raise loudly; the
  caller decides what to do. Guidance Proposition Extractor never substitutes a heuristic result for
  a failed extraction.
- **No Ollama, no flat adapter, no alternative prompts.** Other shapes lost
  the pairwise contest and are out of scope for the production package.

## Usage

```bash
uv sync
export ANTHROPIC_API_KEY=sk-...

# Map an upstream filter run to pages.json (keeps only on-topic URLs)
uv run guidance-proposition-extractor prepare \
  path/to/filter/output.json path/to/pages.json --category slurry
# → pages.json + sibling funnel.json (dropped_not_on_topic with upstream stage)

# Run against a pages.json (the validator-shared shape; see below)
uv run guidance-proposition-extractor run path/to/pages.json path/to/output_dir/
```

`pages.json` is either:

- the validator-shared shape:
  ```json
  {"category": "guidance-pages", "pages": [{"url": "...", "title": "...", "content_id": "..."}]}
  ```
  (`content_id` is threaded from Guidance Relevance Filter via `guidance-proposition-extractor prepare`; optional on hand-written inputs)
- or a plain list of `{url, title}` objects.

`output_dir/` ends up containing:

- `output.json` — a list of `{url, meta_data: {title, candidate_id,
  candidate_name, propositions: [...]}}` entries. This is the shape the
  validators score against.
- `excluded.json` — pages that were **not** extracted, each with a `category`
  (`too_big` or `error`) and a `reason`. Never silently dropped (see below).
- `metrics.json` — tokens and batch-discounted cost, cumulative across resumes.
- `funnel.json` — drop journal. Counts plus URL lists for `extracted`,
  `excluded`, and `not_yet_processed`. `excluded.json` remains the detailed
  too-big/error file; `funnel.json` is the compact inspection view.

### Oversized pages — `too_big` exclusions are expected

Guidance Proposition Extractor caps output at `--max-tokens` (default **8192**). A long, proposition-dense
page — capital-grants manuals, permit-compliance guides, anaerobic-digestion
permit rules — can generate more proposition JSON than that cap, so the response
truncates mid-JSON. Rather than write a half-parsed result, Guidance Proposition Extractor raises
`ExtractionError` and records the page in `excluded.json` under `category:
too_big`. **This is the no-fallback contract working as designed, not a failure:**
a run that extracts a subset and lists the rest as `too_big` is correct behaviour,
and on a corpus skewed toward long guidance a sizeable fraction (e.g. ~1/3) landing
in `excluded.json` is normal.

To pull those pages in, re-run with a higher cap — Guidance Proposition Extractor is resumable, and
`--retry-excluded` re-attempts **only** the `excluded.json` pages (the already
extracted pages are skipped, so you pay only for the retries):

```bash
uv run guidance-proposition-extractor run pages.json out_dir/ --retry-excluded --max-tokens 32000
```

`claude-sonnet-4-6` supports far more than the 8192 default, so raising the cap is
safe. A page that still truncates even at a high cap stays `too_big` — at that
point the page genuinely needs splitting, which is a caller decision, not
something Guidance Proposition Extractor does silently.

## What this isn't

- Not multi-provider. Single API, single model.
- Not wired into any orchestrator. Guidance Proposition Extractor is standalone — wiring is a later,
  separate decision.
- Not a database. JSON in, JSON out.
- Not a workspace member of any monorepo. Standalone `pyproject.toml`.
