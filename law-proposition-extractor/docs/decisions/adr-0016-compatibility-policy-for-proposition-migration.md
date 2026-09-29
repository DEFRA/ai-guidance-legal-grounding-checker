# ADR-0016: Compatibility policy for proposition-first migration

## Status

Accepted

## Context

The architecture is proposition-first, but existing consumers still depend on interim or legacy keys and labels.

## Decision

Canonical naming is proposition-based (`propositions`, `proposition_inventory`, proposition review targets). Compatibility keys from interim terminology (`legal_atoms`, `atom_count`, `atom_ids`, `legal_atom_ids`) are removed from the active bundle/export contract.

## Consequences

The external contract is simpler and terminology is unambiguous. Any consumer still expecting interim keys must migrate to proposition-based fields.
