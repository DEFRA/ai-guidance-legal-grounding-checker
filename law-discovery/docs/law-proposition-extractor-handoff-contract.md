# Law Proposition Extractor handoff contract

Law Discovery exports **selected** (human-accepted) source register entries for **Law Proposition Extractor** to consume later. This document defines the JSON contract only — Law Discovery has **no runtime dependency** on Law Proposition Extractor and is **not part of the Law Proposition Extractor monorepo**.

## Purpose

Law Proposition Extractor turns accepted Law Discovery sources into source-backed legal propositions. Proposition Matcher compares guidance against those propositions. Law Discovery's job ends at curated discovery and handoff.

## Export rules

- Include **`accepted_sources`** from the register only
- Exclude `parked_sources`, `rejected_sources`, and any non-accepted review status
- Do not imply completeness or legal correctness — handoff is a curated candidate set
- Human review is required before export

## Payload shape

```json
{
  "export_type": "ada_selected_sources_for_judit",
  "export_version": "0.1",
  "category_id": "equine_identification",
  "created_at": "2026-05-26T00:00:00Z",
  "sources": []
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `export_type` | string | yes | Constant: `ada_selected_sources_for_judit` |
| `export_version` | string | yes | Contract version, e.g. `"0.1"` |
| `category_id` | string | yes | Category brief id from Law Discovery |
| `created_at` | ISO-8601 datetime | yes | Export timestamp (UTC recommended) |
| `sources` | JuditSource[] | yes | Accepted sources (may be empty) |

## JuditSource

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_id` | string | yes | Law Discovery source id from the register |
| `title` | string | yes | Source title |
| `citation` | string | no | Citation for Law Proposition Extractor display and fetching |
| `source_type` | string | yes | Law Discovery source type enum value |
| `canonical_uri` | string | no | Canonical URI |
| `source_system` | string | yes | Originating system (e.g. `lex`, `gov_uk`) |
| `relationship_to_category` | string | yes | Law Discovery relationship enum |
| `confidence` | string | yes | Law Discovery confidence enum |
| `ada_review_status` | string | yes | Always `"accepted"` in handoff |
| `evidence` | EvidenceSnippet[] | yes | Structured evidence from Law Discovery |

Law Proposition Extractor should treat this payload as **input material to analyse**, not as legal conclusions from Law Discovery.

## Versioning

- `export_version` uses `major.minor`
- Breaking changes increment major; Law Proposition Extractor should reject unknown major versions
- `export_type` distinguishes this contract from other Law Discovery exports

## Law Discovery CLI

```bash
uv run law-discovery export-for-law-proposition-extractor examples/equine-identification.source-register.example.json \
  --output handoff.json
```

## Example

See [examples/selected-sources-for-law-proposition-extractor.example.json](../examples/selected-sources-for-law-proposition-extractor.example.json).

## Relationship diagram

```
Law Discovery repository (standalone)
    │
    │  JSON file: ada_selected_sources_for_judit
    ▼
Law Proposition Extractor (separate product)
    │
    │  propositions
    ▼
Proposition Matcher (separate product)
```
