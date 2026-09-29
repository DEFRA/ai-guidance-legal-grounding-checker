> [!IMPORTANT]
> **Superseded by ADR-0020: Controlled mutation workflows on the operations surface.**
> This ADR remains as historical context for the original read-only v1 workbench decision.

# ADR-0011: Keep the v1 workbench UI read-only

## Status

Accepted

## Context

The current web workbench fetches demo data and presents selectable assessment details but does not provide edit, approve, or mutate actions. UI copy and API surface are aligned to read-only inspection plus export invocation.

## Decision

Law Proposition Extractor v1 UI scope is read-only analysis and review visibility; interactive editing/authoring workflows are deferred.

## Consequences

v1 can ship a stable inspection experience quickly with lower data-integrity risk from partial write paths. Operational review actions still happen outside the web UI until a dedicated mutation workflow is introduced.
