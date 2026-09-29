# Guidance Discovery

**Download all DEFRA guidance gov.uk pages.** Guidance Discovery is the pipeline entry point for
the guidance branch: it discovers
every in-scope gov.uk page and fetches each one's full body text, producing the
page corpus that **Guidance Relevance Filter** then narrows.

Guidance Discovery is two stages, copied near-verbatim from the original `guidance_catalogue`
scripts. It does **no** topic-aware filtering — that is Guidance Relevance Filter's job downstream.

## The two dials — `src/filters.py`

Guidance Discovery's entire selection logic is two static lists, and they live at the top of
[`src/filters.py`](src/filters.py):

- **`ORGANISATIONS`** — the ~45 gov.uk publishing bodies in scope.
- **`DOCUMENT_TYPES`** — the 12 content-store document types that count as guidance.
  HTML-attachment chapters (`html_publication`) are not in this list: the Search API
  does not index them. Stage 2 expands them from each parent publication instead.

There is no query string, no relevance ranking, no date or popularity gate. A page
is pulled if **its org is in `ORGANISATIONS` AND its type is in `DOCUMENT_TYPES`** —
then *every* matching page is fetched in full, **including withdrawn pages**
(Search API `debug=include_withdrawn`; stamped as `meta_data.is_withdrawn`).
Widen the lists for a bigger corpus (longer fetch, higher recall ceiling);
narrow them for a smaller, faster one. These two lists are the only levers on
what the corpus contains.

`filters.py` is *what* we pull. The *how* — endpoints, page size, rate limits,
timeouts, default paths — is named in [`src/config.py`](src/config.py); the page
shape both stages share is in [`src/page.py`](src/page.py). No magic numbers live
in the stage scripts.

## Pipeline

```
  ① discovery (fast)              ② body fetch (the wait)
  get_defra_guidance_pages.py     fetch_body.py
  Search API, metadata only  -->  Content API per URL, plus HTML chapters
  ~19 paged calls, seconds        the Search API never returns
                                  ~18.5k + chapters @ 10 req/s  -->  Guidance Relevance Filter
```

Guidance Discovery uses [`uv`](https://docs.astral.sh/uv/) — the same tool as the other steps.
`uv` reads `pyproject.toml`, installs the right dependencies automatically, and
runs the scripts; you don't need to set up Python yourself. The whole corpus build
is one command:

```bash
./run.sh                                       # stage 1 then stage 2, default paths
```

Or run the stages individually. Both default their paths from `config.py`, so the
no-argument runs chain end-to-end. **Stage 1 — `src/get_defra_guidance_pages.py`**
queries the GOV.UK Search API using the two dials and writes pipeline-format JSON
(metadata only, **no** body text). It fails loudly: a non-200 response or a result
count that disagrees with the API's reported total aborts rather than writing a
truncated corpus.

```bash
uv run python src/get_defra_guidance_pages.py  # -> output/search_api.json
```

**Stage 2 — `src/fetch_body.py`** takes that file, calls the GOV.UK Content API once
per URL, and adds `meta_data.body_text`. Body text comes from `details.body` /
`details.parts` when those have prose; collections and manuals synthesize an
index from `collection_groups` / `child_section_groups` plus member titles
(their visible page is a TOC, not a `details.body`). Publication parents also get
their `html_publication` chapters expanded from `links.children` and appended as
extra items (Search API never returns that type). Restartable — already-fetched
URLs with a non-empty body are skipped on re-run, except publication parents whose
cache predates expansion (missing `html_publication_urls`) which are re-fetched
once so chapters appear. Failed or empty bodies are retried.
The final summary loudly counts any pages whose fetch failed (`body_text` null),
since those are invisible to Guidance Relevance Filter:

```bash
uv run python src/fetch_body.py                # output/search_api.json -> output/with_body.json
# or override: uv run python src/fetch_body.py IN.json OUT.json --concurrency 3 --rate 10.0
```

The search is cheap (~19 requests); the cost is stage 2 fetching every body
one-by-one at a polite rate — that is the "sit and wait", and `--rate` /
`--concurrency` are the speed-vs-politeness dials.

Stage 2 also writes `output/funnel.json` next to `with_body.json`: counts plus
URL lists for `fetch_failed` (with `fetch_error.http_status` / `error`),
`body_empty`, `chapters_expanded` (new HTML-publication URLs, with `parent_url`),
and `search_hits_missing_from_output` (should be empty; a silent drop if not).
Failed fetches are stamped `meta_data.body_text=null` + `meta_data.fetch_error`
on the page itself so Guidance Relevance Filter can split missing-body from
empty-body.

### Outputs / caching

The corpus JSON files **are** the cache: stage 2 reads `with_body.json` and skips URLs
already fetched with a non-empty body, so a re-run retries failures and empty
bodies. `funnel.json` is an inspection sidecar, not a cache. They're run artifacts
(the real home for them is `content-audit-data-assets`), so `output/` is git-ignored.

## Output shape

Stage 2's output is exactly Guidance Relevance Filter's expected input — discovery metadata plus
`body_text`:

```json
[
  {
    "url": "https://www.gov.uk/...",
    "content_id": "...",
    "meta_data": {
      "title": "...",
      "description": "...",
      "updated_at": "...",
      "document_type": "...",
      "view_count": 0,
      "organisations": ["department-for-environment-food-rural-affairs"],
      "primary_publishing_organisation": "department-for-environment-food-rural-affairs",
      "is_withdrawn": false,
      "body_text": "..."
    }
  }
]
```

## Tests

```bash
uv run pytest
```

A small suite over the pure logic in each stage: stage 1's Search-hit → page
contract mapping (`to_pipeline_item`) and stage 2's body-text extraction
(`_extract_body_text`) plus HTML-chapter expansion helpers. They run offline —
no network calls.

## Dependencies

Just `httpx` and `typer` at runtime, declared in `pyproject.toml` and pinned in
`uv.lock` (`pytest` is a dev-only dependency). Guidance Discovery needs no API keys or `.env` —
both stages only hit public gov.uk endpoints.
