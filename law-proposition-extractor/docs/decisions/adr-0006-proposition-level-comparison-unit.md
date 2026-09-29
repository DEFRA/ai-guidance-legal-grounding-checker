# ADR-0006: Use propositions as canonical analysis unit

## Status

Accepted

## Context

Domain and pipeline models must support both single-jurisdiction analysis and divergence workflows.
`Proposition` is the primary, source-backed analysis entity.
Divergence records link proposition pairs (`proposition_id` and `comparator_proposition_id`) and remain downstream artifacts.

## Decision

Law Proposition Extractor performs legal analysis at proposition level, not whole-document level.
Single-jurisdiction proposition inventory is first-class.
Cross-jurisdiction divergence is built on top of propositions rather than defining the entire architecture.

## Consequences

Proposition outputs are useful independently of divergence use-cases.
Comparisons remain precise and traceable to specific legal statements, enabling targeted rationale and review.
Document-level outputs are derived views built from proposition-level records.
