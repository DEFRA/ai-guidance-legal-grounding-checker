# Law Proposition Extractor

Law Proposition Extractor is a source-first, proposition-first legal analysis workbench.
It supports single-jurisdiction proposition inventory as a first-class workflow and
builds divergence comparison on top of that substrate.

![Core workflow](assets/generated/diagrams/core-workflow.svg)

*Figure: Core Law Proposition Extractor workflow from authoritative legal sources through SourceRecord, SourceSnapshot, SourceFragment, proposition extraction, Proposition inventory, reviewable context, and outputs.*

Generated outputs are committed alongside their sources. Run `just docs-refresh` to regenerate everything from sources.

## v1 focus

- source register
- source registry and registry-driven runs
- proposition inventory and review workflow
- divergence workflow built on propositions
- operational UI and analysis UI split
- operations/audit surface with temporal history inspection
- local/cloud model routing through LiteLLM
- export bundle for static rendering / ops loading
- explainability handbook (`docs/explainability/`) with DecisionExplanation coverage

## Technical architecture

![Technical architecture](assets/generated/diagrams/technical-architecture.svg)

*Figure: Runtime structure across workbench and operations surfaces, FastAPI API, source registry, pipeline runner, caches, LiteLLM, and run artifacts/traces/export bundle.*

## Temporal traceability

![Temporal audit](assets/generated/diagrams/temporal-audit.svg)

*Figure: Temporal lineage for source snapshots, propositions, divergence entities, and review decisions with source-fragment traceability.*

## Where to go next

- Architecture: [Pipeline overview](architecture/pipeline-overview.md) - [Proposition classification](architecture/proposition-classification.md) - [System overview](architecture/system-overview.md) - [Effective-law layers](architecture/effective-law-layers.md)
- Explainability: [Handbook index](explainability/README.md) - [Concepts](explainability/concepts.md) - [Pipeline](explainability/pipeline.md) - [Diagrams](explainability/diagrams.md) - [Heuristics](explainability/heuristics.md) - [Article 49a walkthrough](explainability/article-49a-walkthrough.md) - [Structural-source fixtures](explainability/structural-source-fixtures.md) - [Proposition-fidelity benchmark](explainability/proposition-fidelity-benchmark.md)
- Reference: [Artifacts](reference/artifacts.md) - [Ops API](reference/api-ops.md) - [CLI](reference/cli.md)
- Operator guides: [Source registry](dev/source-registry.md) - [Extraction repair](dev/extraction-repair.md) - [Review governance](dev/review-governance.md) - [Review Workbench calibration](review-workbench-calibration.md) - [Equine staged runs](dev/equine-passport-staged-runs.md)
- Visuals: [Diagrams](assets/diagrams/README.md) - [Infographics](assets/infographics/README.md) - [Decks](assets/decks/README.md) - [Generated assets inventory](assets/generated-assets.md)
- Roadmap: [Canonical roadmap](canonical/roadmap.md) - [v1](roadmap/v1.md)
