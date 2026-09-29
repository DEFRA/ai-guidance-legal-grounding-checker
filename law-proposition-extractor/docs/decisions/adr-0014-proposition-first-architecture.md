# ADR-0014: Proposition-first architecture

## Status

Accepted

## Context

Law Proposition Extractor must support legal analysis value even when cross-jurisdiction divergence is not requested.

## Decision

`Proposition` is the canonical core entity. Source-backed proposition inventory, categorization, cross-reference structure, and review status are first-class outputs. Divergence workflows are downstream analyses built on propositions.

## Consequences

Single-jurisdiction runs produce useful outputs without divergence. Divergence remains supported but no longer defines the system boundary.

Machine identity vs human-readable naming for propositions is specified in ADR-0018.
