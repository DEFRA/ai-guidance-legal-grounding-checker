# Law Discovery V1 process

V1 is a CLI-driven pipeline from category brief to exportable source register and optional Law Proposition Extractor handoff. Law Discovery is standalone; Law Proposition Extractor consumes exports asynchronously via JSON.

## V1 scope

| Capability | Required? | Notes |
|------------|-----------|-------|
| Category brief input | yes | JSON file; see example category |
| Deterministic query-plan generation | yes | No AI required |
| Lex API / Lex Graph discovery | yes | First discovery substrate; fixtures in tests |
| Candidate source normalisation | yes | Common `SourceCandidate` shape |
| Simple deterministic scoring | yes | Keyword/synonym overlap, exclusion penalty |
| Optional Pydantic AI category expansion | no | Requires LiteLLM proxy |
| Optional Pydantic AI relevance assessment | no | Structured rationale into Pydantic models |
| AI routed through LiteLLM | default | When AI is enabled |
| Human review status | yes | `unreviewed`, `parked`, `accepted`, `rejected`, `needs_more_research` |
| JSON source register export | yes | Canonical Law Discovery output |
| Selected-sources handoff for Law Proposition Extractor | yes | Accepted entries only |
| Related-source expansion around accepted seeds | yes | Search-based v1; optional AI relationship triage |
| Source bundle export for Law Proposition Extractor | yes | Buckets + relationships; no legal effect resolved |

## V1 non-goals

- No guarantee of completeness
- No final legal conclusions or legal advice
- No proposition extraction
- No guidance/law comparison
- No database
- No web UI
- No direct dependency on Law Proposition Extractor code

## End-to-end flow

```mermaid
flowchart LR
  A[Category brief] --> B[Query plan]
  B --> C[Lex discovery]
  C --> D[Normalise + score]
  D --> E[Optional AI assessment]
  E --> F[Register draft]
  F --> G[Human review]
  G --> H[Export register]
  G --> I[Export Law Proposition Extractor handoff]
```

### 1. Define category brief

Create a JSON file with `category_id`, `label`, `description`, `synonyms`, optional `exclusions` and `jurisdiction_hints`.

Example: [examples/equine-identification.category.json](../examples/equine-identification.category.json)

### 2. Validate category brief

Load and inspect the category JSON, or build a query plan directly:

```bash
uv run law-discovery build-query-plan examples/equine-identification.category.json
```

### 3. Generate query plan

```bash
uv run law-discovery build-query-plan examples/equine-identification.category.json \
  --output query-plan.json
```

Builds a deterministic plan from synonyms and exclusions. No network or AI required.

### 4. Optional category expansion (AI)

When `LAW_DISCOVERY_AI_*` and LiteLLM env vars are set, Law Discovery may suggest additional synonyms or search terms. Output validates into a Pydantic model (see [equine-expansion.example.json](../examples/equine-expansion.example.json)).

Deterministic fallback when AI is not configured.

### 5. Discover candidates

```bash
uv run law-discovery discover examples/equine-identification.category.json \
  --output run.json \
  --no-network
```

For live Lex discovery, omit `--no-network` and configure `LAW_DISCOVERY_LEX_BASE_URL`.

Queries Lex API / Lex Graph via the Lex adapter. Returns normalised candidates with deterministic scores.

**Lex is a discovery substrate, not canonical legal truth.** Candidates require human review.

### 6. Build and review source register

Use `make-register` to split discovery candidates into register buckets. Reviewers move sources between `accepted_sources`, `rejected_sources`, and `parked_sources`, and may add `notes`.

Review statuses on `CandidateSource`:

- **unreviewed** — default from discovery
- **parked** — default from `make-register` (awaiting review)
- **accepted** — eligible for Law Proposition Extractor handoff
- **rejected** — excluded from handoff
- **needs_more_research** — requires further investigation

### 7. Export register and Law Proposition Extractor handoff

```bash
uv run law-discovery make-register run.json --output register.json
uv run law-discovery export-for-law-proposition-extractor register.json --output handoff.json
```

Exports **accepted** entries only, using the contract in [law-proposition-extractor-handoff-contract.md](law-proposition-extractor-handoff-contract.md).

## Non-AI path

Steps 1–3, 5–7 work with zero AI configuration. Query planning and scoring are fully deterministic.

## Testing

Unit tests use Lex fixtures and skip live model calls. `pytest` requires no network access.
