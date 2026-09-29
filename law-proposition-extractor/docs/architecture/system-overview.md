# System overview

Law Proposition Extractor is a source-first, proposition-first legal analysis workbench.

## Product model

Law Proposition Extractor structures legal analysis around:

- sources (authoritative legal texts)
- propositions (atomic legal statements)
- context (instrument, article, conditions)
- scopes (legal domains such as equine, bovine)
- divergence (differences across jurisdictions or time)

Law Proposition Extractor has four main layers:

1. pipeline and storage
2. LLM gateway
3. analysis + operations surfaces (API/UI)
4. docs and export assets

![Technical architecture diagram](../assets/generated/diagrams/technical-architecture.svg)

*Figure: Clear architecture boundaries across product surfaces, FastAPI API orchestration, source registry, pipeline runner, caches, LiteLLM, and run artifacts/traces/export bundle.*

Generated assets may be absent in a clean checkout. Run `just docs-refresh` to regenerate them.

## Pipeline model involvement

Law Proposition Extractor uses a deterministic-first pipeline with controlled model usage:

- Most stages do not use language models
- Proposition extraction may use a local model
- Divergence reasoning may optionally use a frontier model
- All model usage is traceable via stage traces

**Proposition identity (ADR-0018).** Machine identity (`Proposition.id`) is opaque and stable. Source lineage uses `proposition_key` (`<instrument-id>:<fragment-locator>:pNNN` when derived from registered sources). Human-readable names use `label` and `short_name`; `slug` is for routing only and is not durable identity.

**Pipeline model involvement (ADR-0019).** Processing is deterministic-first: language models are used only in explicitly defined stages, with traces persisted in run artifacts so operators can see what ran. Stage-by-stage behaviour and model boundaries are documented in the [pipeline overview](./pipeline-overview.md); the decision record is [ADR-0019: Model usage strategy](../decisions/adr-0019-model-usage-strategy.md). A stakeholder-facing summary for visuals and comms lives in [Pipeline infographic brief](../assets/infographics/pipeline-overview.md).

The core domain substrate is source-first and proposition-first:

- source registry + source intake (record/snapshot/fragment)
- proposition inventory as first-class output
- divergence workflows as downstream proposition pairing/classification

Workflow truth:

- `single_jurisdiction` is a first-class analysis mode
- `divergence` mode is enabled explicitly or inferred when multi-jurisdiction input is present
- pairing/classification stages emit explicit skip traces when divergence is not active

UI/API surface truth:

- analysis UI (`/`) is focused on read-only proposition/divergence analysis views
- operations UI (`/ops`) is focused on registry, run artifacts, and operational workflows
- operations surface is read-mostly with selected controlled mutation workflows:
  registry management, review decisions, async run jobs, extraction repair, and dev reset controls
- both surfaces rely on persisted run artifacts and `/ops/*` endpoints for inspection and controlled writes

Operational/audit truth:

- run-scoped manifests, artifacts, and stage traces are persisted under `dist/static-report/runs/<run-id>/`
- source registry state is persisted separately and can be inspected/refreshed through API endpoints
- history inspection is available for:
  - sources (`/ops/sources/{source_id}/history`, `/timeline`, `/snapshots`)
  - propositions (`/ops/propositions/{proposition_key}/history`)
  - divergence findings (`/ops/divergence-findings/{finding_id}/history`)

The export bundle remains a first-class boundary so future static renderers can consume validated output without owning business logic.

![Temporal audit architecture](../assets/generated/diagrams/temporal-audit.svg)

*Figure: Temporal history model linking SourceSnapshot, Proposition, DivergenceObservation, DivergenceFinding, and review decision traceability.*
