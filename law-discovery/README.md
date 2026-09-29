# Law Discovery — UK legal source discovery

![Law Discovery pipeline: category brief through discovery, review, and export to Law Proposition Extractor and Proposition Matcher](ada_infographic.png)

Law Discovery is a **standalone** legal source discovery workbench. Given a category brief, Law Discovery finds **candidate** UK legal instruments and interpretive materials, scores them deterministically, supports human review, and exports a source register and Law Proposition Extractor handoff JSON.

Law Discovery is **not** part of the Law Proposition Extractor monorepo and has **no runtime dependency** on Law Proposition Extractor or Proposition Matcher code.

## Relationship to Law Proposition Extractor and Proposition Matcher

| Product | Role |
|---------|------|
| **Law Discovery** | Finds candidate legal sources and helps curate a reviewable register |
| **Law Proposition Extractor** | Extracts source-backed legal propositions from accepted Law Discovery sources |
| **Proposition Matcher** | Checks guidance against Law Proposition Extractor propositions |

Law Discovery does **not** make legal conclusions, extract propositions, or compare guidance against law.

## What Law Discovery does not guarantee

Law Discovery does **not** guarantee complete legal coverage. Lex results are **candidates**, not canonical legal truth. Human review is required before exporting sources for Law Proposition Extractor.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

Copy `.env.example` to `.env` when using Lex-backed discovery or AI-assisted workflows. Deterministic `--no-network` commands work without Lex or LiteLLM configuration.

## Quality checks

```bash
uv run pytest
uv run ruff check .
uv run basedpyright
```

## CLI overview

```bash
uv run law-discovery --help
```

| Command | Purpose |
|---------|---------|
| `build-query-plan` | Build deterministic search plan from a category brief |
| `expand-category` | AI-assisted category expansion (requires LiteLLM) |
| `discover` | Run discovery and write a `DiscoveryRun` |
| `make-register` | Build a `SourceRegister` from a discovery run |
| `export-for-law-proposition-extractor` | Export accepted sources for Law Proposition Extractor handoff JSON |
| `expand-related-sources` | Discover related materials around accepted register sources |
| `make-source-bundle` | Build a structured `SourceBundle` from register + related expansion |
| `export-bundle-for-law-proposition-extractor` | Export bundle with relationships for richer Law Proposition Extractor handoff |
| `law-discovery-viewer` | Local Streamlit UI to review discovery runs, related expansion, or bundles |

## Reviewing a discovery run

Review candidates in a discovery run without editing the original JSON on disk. Session state holds review decisions; download a `SourceRegister` or Law Proposition Extractor handoff JSON when ready.

```bash
uv run law-discovery-viewer runs/animal_by_products/discovery-run.json
```

Equivalent:

```bash
uv run streamlit run src/law-discovery/viewer.py -- runs/animal_by_products/discovery-run.json
```

## Deterministic no-network workflow

No Lex, LiteLLM, or provider credentials required.

```bash
uv run law-discovery build-query-plan examples/equine-identification.category.json \
  --output /tmp/equine-query-plan.json

uv run law-discovery discover examples/equine-identification.category.json \
  --output /tmp/equine-discovery-run.json \
  --no-network

uv run law-discovery make-register /tmp/equine-discovery-run.json \
  --output /tmp/equine-source-register.json

uv run law-discovery export-for-law-proposition-extractor /tmp/equine-source-register.json \
  --output /tmp/selected-sources-for-law-proposition-extractor.json
```

Review and update the source register before export. By default, `make-register` places all candidates in `parked_sources`. Use `--accept-high-confidence` only when you intentionally want high-confidence candidates pre-placed in `accepted_sources` for review.

## Lex-backed workflow

Lex is a **candidate discovery substrate**, not canonical legal truth. Law Discovery calls `POST {LAW_DISCOVERY_LEX_BASE_URL}/legislation/search` with a JSON body containing `query` and `limit`.

```bash
export LAW_DISCOVERY_LEX_BASE_URL="<lex-base-url>"
export LAW_DISCOVERY_LEX_API_KEY="<optional-key>"

uv run law-discovery discover examples/equine-identification.category.json \
  --output /tmp/equine-discovery-run.json
```

Or pass overrides on the command line:

```bash
uv run law-discovery discover examples/equine-identification.category.json \
  --output /tmp/equine-discovery-run.json \
  --lex-base-url "<lex-base-url>" \
  --lex-api-key "<optional-key>"
```

## AI-assisted workflow (Pydantic AI + LiteLLM)

Law Discovery uses **Pydantic AI** as the typed AI layer and routes all model calls through a **LiteLLM OpenAI-compatible proxy**. Law Discovery does **not** call OpenAI, Anthropic, Google, Gemini, Ollama, LiteLLM SDK, or other provider SDKs directly from application code.

```bash
export LAW_DISCOVERY_AI_PROVIDER=litellm
export LAW_DISCOVERY_AI_MODEL=law-discovery-fast
export LAW_DISCOVERY_LITELLM_BASE_URL=http://localhost:4000/v1
export LAW_DISCOVERY_LITELLM_API_KEY=sk-local-dev

uv run law-discovery expand-category examples/equine-identification.category.json \
  --output /tmp/equine-expansion.json

uv run law-discovery build-query-plan examples/equine-identification.category.json \
  --expansion /tmp/equine-expansion.json \
  --output /tmp/equine-query-plan.json

uv run law-discovery discover examples/equine-identification.category.json \
  --expansion /tmp/equine-expansion.json \
  --use-ai-assessment \
  --output /tmp/equine-discovery-run.json
```

AI assessment never auto-accepts or auto-rejects sources for Law Proposition Extractor export.

## Related source expansion

After you have an accepted (or high-confidence parked) source register, Law Discovery can expand around those **seed** sources to discover surrounding legal and interpretive materials: amendments, commencement orders, revocations, correction slips, explanatory notes, impact assessments, guidance, forms, and similar.

**Product boundary:** Law Discovery discovers and labels the source universe and relationships. Law Discovery does **not** determine final legal effect. Law Proposition Extractor resolves legal effect, versioning, commencement, extent, amendments, and extracts propositions.

```fish
set -gx LAW_DISCOVERY_AI_MODEL frontier_reason
set -gx LAW_DISCOVERY_LITELLM_BASE_URL http://localhost:4000/v1
set -gx LAW_DISCOVERY_LITELLM_API_KEY sk-local-dev

uv run law-discovery expand-related-sources \
  runs/equine_passports/source-register.json \
  examples/categories/equine_passports.category.json \
  --output runs/equine_passports/related-sources-run.json \
  --use-ai-triage

uv run law-discovery make-source-bundle \
  runs/equine_passports/source-register.json \
  --related-run runs/equine_passports/related-sources-run.json \
  --output runs/equine_passports/source-bundle.json

uv run law-discovery export-bundle-for-law-proposition-extractor \
  runs/equine_passports/source-bundle.json \
  --output runs/equine_passports/source-bundle-for-law-proposition-extractor.json
```

Deterministic `--no-network` mode builds the related query plan and seed list without Lex calls (useful for CI and offline planning).

Review related expansion or bundles in the viewer:

```fish
uv run law-discovery-viewer runs/equine_passports/related-sources-run.json
uv run law-discovery-viewer runs/equine_passports/source-bundle.json
```

## Architecture notes

```
Category brief
    → query plan (deterministic)
    → Lex search (optional, candidate generator)
    → normalise + score + dedupe
    → optional Pydantic AI assessment via LiteLLM proxy
    → human review
    → source register
    → selected-sources-for-law-proposition-extractor JSON handoff

Accepted / likely-accepted sources
    → related-source query plan (deterministic)
    → Lex search for related materials
    → relationship classification (+ optional AI triage)
    → human review
    → source bundle
    → source-bundle-for-law-proposition-extractor JSON handoff (richer than selected-sources export)
```

- **Lex** — candidate generator; not treated as canonical legal truth
- **Pydantic AI** — typed agents and structured outputs validated into Pydantic models
- **LiteLLM** — model gateway (OpenAI-compatible HTTP proxy)
- **Law Proposition Extractor** — consumes handoff JSON later; not a dependency of this repository

## Documentation

- [Product brief](docs/product-brief.md)
- [V1 process](docs/v1-process.md)
- [Source register schema](docs/source-register-schema.md)
- [Law Proposition Extractor handoff contract](docs/law-proposition-extractor-handoff-contract.md)
- [LiteLLM integration](docs/litellm.md)
- [Lex API notes](docs/lex-api-notes.md)

## License

Internal — DEFRA.
