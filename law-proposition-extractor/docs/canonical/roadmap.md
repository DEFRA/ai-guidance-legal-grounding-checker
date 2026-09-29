# Roadmap

## v1 — Proposition-first analysis (current)

### Product capabilities

- proposition-first legal analysis domain model
- source-first ingestion via source registry references
- single-jurisdiction proposition inventory workflow
- divergence workflow built on propositions as downstream mode
- reviewable proposition interface (propositions screen)
- operations and history APIs for runs, sources, traces, and decisions

### Pipeline capabilities

- source fetch attempts and snapshot integrity tracking
- parser and fragment-level traceability
- structured source inventory with roles and relationships
- explicit source target-link semantics
- categorisation rationale with evidence and confidence
- scope (legal area) taxonomy with deterministic proposition linking
- proposition extraction traceability
- proposition completeness assessment (context-aware display)
- run quality summary and lint-based quality gates
- pipeline review decision system (human-in-the-loop governance)
- run comparison and regression detection

### System infrastructure

- workspace bootstrap and API shell with core domain models
- FastAPI backend
- export bundle and static report
- operations/registry inspector (`/ops`)
- analysis workbench (`/`)
- LiteLLM gateway
- docs site with architecture visuals and diagrams
- Marp deck support

For pipeline shape, model-usage boundaries, and stakeholder-facing explanation, see the [architecture pipeline overview](../architecture/pipeline-overview.md), [ADR-0019](../decisions/adr-0019-model-usage-strategy.md), and [pipeline infographic brief](../assets/infographics/pipeline-overview.md).

## v1.5 — Reviewable structured propositions (current consolidation)

**Goal:** Improve proposition review quality and readability before investing in relationship navigation or temporal views.

**Product and analysis direction**

- improve structured proposition reliability (extraction and display consistency)
- add **provision type** classification:
  - core rule
  - definition
  - exception
  - transitional
  - cross-reference
- reduce noisy scope links by hiding contextual / low-confidence links by default (reviewer can expand when needed)
- allow review decisions on:
  - proposition
  - structured proposition display
  - scope links
  - completeness assessment
- **group propositions by article / provision** as the primary navigation pattern; this must be dependable before any timeline-style views

**Status snapshot (2026-05, factual)**

- structured proposition reliability: implemented, tested, operator-friendly gap
- provision type classification/surfacing: implemented, tested, documented
- review decisions on proposition/structured display/scope links/completeness: implemented, tested, documented
- proposition grouping by article/provision: implemented, tested, documented
- timeline view: planned

**Explicitly not in v1.5**

- timeline view of legal change (deferred; see Future)

## v2 — Context and relationship navigation

Builds on reliable structured propositions, provision types, and article-level grouping.

- article-level proposition clusters
- related provisions
- related sources
- cross-reference navigation
- comparison across jurisdictions and time (where sources support it)

## Future

- timeline view of legal change and transitional provisions
- “what applies now / later” views
- temporal reasoning across versions and instruments

## Explicitly deferred

- **Timeline / temporal product UI** until structured propositions, provision types, and article-level grouping are reliable (covered under v1.5 → v2 sequencing above)
- LangSmith evaluation
- Astro renderer implementation
- Slidev
- advanced orchestration
