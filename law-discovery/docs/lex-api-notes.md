# Lex API and Lex Graph notes

Lex (Legislation EXplorer / legislation.gov.uk APIs and Lex Graph) is Law Discovery's **first candidate source discovery substrate** in V1. Law Discovery queries Lex to find **candidates** for human review — not to assert canonical legal truth.

## Role in Law Discovery

| Concern | Lex role |
|---------|----------|
| Discovery | Primary substrate for finding instruments and related materials |
| Normalisation | Lex ids and URIs attached to candidates |
| Canonical truth | **Not Lex** — human review and Law Proposition Extractor analysis follow |

```
Category brief → query plan → Lex API / Lex Graph → normalised candidates → scoring → register
```

Lex results are **candidates**. A high Lex relevance score does not mean the source is legally determinative or complete for the category.

## Adapter

Implementation: `law-discovery.lex_adapter.LexAdapter`

Responsibilities:

- Translate query plan items into Lex legislation search requests
- Support Lex API legislation search and (where configured) Lex Graph queries
- Normalise responses into `SourceCandidate` Pydantic models
- Accept injectable HTTP transports for offline tests

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `{base_url}/legislation/search` | `POST` | Legislation search (V1) |
| `{base_url}/legislation/section/search` | `POST` | Section search (planned) |

Legislation search request body:

```json
{
  "query": "<search terms>",
  "limit": 10
}
```

Optional auth header when `LAW_DISCOVERY_LEX_API_KEY` is set:

```http
Authorization: Bearer <key>
Content-Type: application/json
```

## Environment variables

```bash
LAW_DISCOVERY_LEX_BASE_URL=<lex base url>
LAW_DISCOVERY_LEX_API_KEY=<optional key>
```

| Variable | Required | Description |
|----------|----------|-------------|
| `LAW_DISCOVERY_LEX_BASE_URL` | for live discovery | Base URL for Lex API / Graph endpoint |
| `LAW_DISCOVERY_LEX_API_KEY` | no | API key when the Lex deployment requires auth |

If unset, `discover` without `--no-network` fails immediately with a clear error. Use `--no-network` for offline runs, or set `LAW_DISCOVERY_LEX_BASE_URL` / `--lex-base-url` for live discovery.

## V1 behaviour

- Search by synonym/term from the query plan
- Map Lex document types to Law Discovery `source_type` enum
- Capture `lex_id`, `uri`, title, citation, optional snippet
- Tag `discovery_method` as `lex_api` or `lex_graph`
- Set `discovery_substrate: "lex"` on register entries

Out of scope for V1:

- Full statute text parsing
- Guarantee of search completeness
- Treating Lex metadata as legal advice

## Testing

```python
LexAdapter(base_url="https://lex.example.test", transport=httpx.MockTransport(handler))
```

Unit tests never call live Lex. See `tests/test_lex_adapter.py`.

## Completeness disclaimer

Law Discovery V1 does **not** guarantee that Lex discovery finds every relevant instrument. Reviewers may add manual entries or defer candidates. Completeness is a human workflow concern, not an Law Discovery promise.

## Future considerations

- Pagination and rate limiting
- Jurisdiction filters from `jurisdiction_hints`
- Secondary legislation and guidance-specific endpoints
- Optional caching (still no core database in V1)
