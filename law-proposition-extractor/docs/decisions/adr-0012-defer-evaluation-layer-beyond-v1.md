# ADR-0012: Defer the evaluation layer beyond v1

## Status

Accepted

## Context

Roadmap and canonical project-state documents explicitly list LangSmith evaluation as planned/deferred, while v1 scope focuses on pipeline, API, docs, and export bundle delivery.

## Decision

Evaluation infrastructure (for example LangSmith run evaluation and regression datasets) is intentionally out of v1 scope and scheduled for later phases.

## Consequences

v1 delivery stays focused on core comparison and export architecture, reducing implementation surface. Formal quality measurement and regression benchmarking must be added as a follow-on capability before scaling decision automation.
