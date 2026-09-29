# ADR-0017: Treat operational history APIs as a first-class architecture boundary

## Status

Accepted

## Context

Law Proposition Extractor now persists run-scoped artifacts and exposes read-only operational endpoints for runs, traces, source records, registry entries, and temporal history inspection for sources, propositions, and divergence findings. These endpoints are consumed by the workbench and are part of the practical operator workflow.

## Decision

The `/ops/*` surface and run artifact layout are part of the architecture contract for v1:

- run-scoped manifests/artifacts/traces under `dist/static-report/runs/<run-id>/`
- source registry state as a persisted control plane for source-first runs
- history inspectors for source snapshots, proposition versions, and divergence finding versions

Changes to these contracts require explicit migration planning and compatibility review.

## Consequences

Operational visibility is stable, auditable, and scriptable across CLI/API/UI touchpoints. Future UI changes can iterate quickly without redefining storage shape or endpoint semantics. Contract evolution becomes more deliberate, with higher migration discipline.
