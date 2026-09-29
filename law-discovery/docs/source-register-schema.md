# Source register schema

The **source register** is Law Discovery's primary curated output: a reviewable list of candidate UK legal sources for one category. It is versioned JSON, not a database table.

Law Discovery does **not** assert that the register is complete or legally authoritative.

## Register document (`SourceRegister`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `register_id` | string | yes | Stable register identifier |
| `category_id` | string | yes | Category brief id (snake_case) |
| `created_at` | ISO-8601 datetime | yes | Register creation time |
| `accepted_sources` | `CandidateSource[]` | yes | Human-accepted sources (may be empty) |
| `rejected_sources` | `CandidateSource[]` | yes | Rejected sources (may be empty) |
| `parked_sources` | `CandidateSource[]` | yes | Parked / awaiting review (may be empty) |
| `export_target` | string | no | Default `"law-proposition-extractor"` |
| `metadata` | object | no | Pipeline metadata (e.g. discovery run id) |

### Example top-level shape

See [equine-identification.source-register.example.json](../examples/equine-identification.source-register.example.json).

## CandidateSource

Each register bucket holds full `CandidateSource` records (same shape as discovery run candidates).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_id` | string | yes | Stable id within Law Discovery (`lex-{sha256}` of normalised legislation.gov.uk URI when applicable) |
| `title` | string | yes | Display title |
| `citation` | string | no | Human-readable citation |
| `source_type` | enum | no | e.g. `uksi`, `ukpga`, `guidance`, `unknown` |
| `canonical_uri` | string | no | Canonical URI (e.g. legislation.gov.uk) |
| `source_system` | enum | no | e.g. `lex`, `gov_uk`, `manual` |
| `jurisdiction_extent` | string[] | no | Jurisdiction hints from source metadata |
| `temporal_status` | enum | no | e.g. `current`, `revoked`, `unknown` |
| `relationship_to_category` | enum | no | e.g. `directly_regulates`, `operationalises` |
| `match_basis` | string[] | no | How the candidate matched (e.g. `lex_search`) |
| `matched_terms` | string[] | no | Synonyms/keywords that matched |
| `evidence` | `EvidenceSnippet[]` | no | Structured evidence snippets |
| `confidence` | enum | no | `high`, `medium`, `low`, `unknown` |
| `review_status` | enum | no | Human or pipeline review status |
| `notes` | string | no | Reviewer or AI notes |

### `review_status` enum

| Status | Meaning |
|--------|---------|
| `unreviewed` | Default from discovery; not yet reviewed |
| `parked` | Awaiting human review (default from `make-register`) |
| `accepted` | Approved for potential Law Proposition Extractor handoff |
| `rejected` | Excluded from handoff |
| `needs_more_research` | Requires further investigation |

Only sources in `accepted_sources` appear in the Law Proposition Extractor handoff export.

## Discovery run (`DiscoveryRun`)

A discovery run captures pipeline output before register curation. See [equine-identification.discovery-run.example.json](../examples/equine-identification.discovery-run.example.json).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | yes | Run identifier |
| `created_at` | ISO-8601 datetime | yes | Run timestamp |
| `category` | `CategoryBrief` | yes | Embedded category brief |
| `query_plan` | `DiscoveryQuery[]` | yes | Plan used for this run |
| `candidate_sources` | `CandidateSource[]` | yes | Normalised, scored candidates |
| `warnings` | string[] | no | Non-fatal pipeline warnings |
| `metadata` | object | no | e.g. `use_network`, `candidate_count` |

## Category brief (`CategoryBrief`)

See [equine-identification.category.json](../examples/equine-identification.category.json).

| Field | Type | Required |
|-------|------|----------|
| `category_id` | string | yes |
| `label` | string | yes |
| `description` | string | yes |
| `synonyms` | string[] | no |
| `exclusions` | string[] | no |
| `jurisdiction_hints` | string[] | no |
| `metadata` | object | no |

## Implementation note

Pydantic types in `law-discovery.models` are the source of truth. Example JSON files in `examples/` validate against those models.
