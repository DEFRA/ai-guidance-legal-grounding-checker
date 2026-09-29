# Law Proposition Extractor infographic prompt context

This file is generated from canonical state docs for prompt authoring.
Do not edit manually.

## docs/canonical/project-state.md

# Project state (canonical)

## App metadata

- name: `Law Proposition Extractor`
- version: `v1`
- status: `in-development`

## Implemented

- source register and source registry API workflows
- source snapshot and fragment tracking
- proposition inventory register
- workflow modes: `single_jurisdiction` first, `divergence` downstream
- operations/audit API surface
- temporal history inspection for sources, propositions, and divergence findings
- export bundle boundary for static rendering
- LiteLLM gateway for local/cloud model routing
- UI split: analysis workbench and operations/registry inspector
- D2-authored architecture diagrams
- Marp-authored deck sources

## Planned

- Astro static renderer
- LangSmith evaluation layer
- Slidev interactive deck layer

## docs/canonical/roadmap.md

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

## docs/canonical/audiences.md

# Audiences (canonical)

## Technical

Focus on:

- architecture boundaries
- data schemas and contracts
- model routing and operational controls
- export contract stability

## Non-technical

Focus on:

- trustworthy and reviewable workflow
- operational transparency
- clear outputs and evidence chain
- roadmap and delivery confidence

## docs/canonical/visuals.md

# Visuals guidance (canonical)

## Visual intent

- show future layers: `true`
- tone: polished, clear, high-signal
- audience mix: technical + non-technical

## Must-show v1 architecture elements

- source registry as control plane
- proposition inventory as first-class output
- divergence workflow as downstream/optional mode
- operations/audit surface and temporal history inspection
- export bundle boundary

## Future layers to show as deferred

- Astro static renderer
- LangSmith evaluation
- Slidev demos

