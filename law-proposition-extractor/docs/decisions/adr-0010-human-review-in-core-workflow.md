# ADR-0010: Keep human review as a core workflow artifact

## Status

Accepted

## Context

Review status is embedded across source fragments, propositions, and divergence observations.
The pipeline emits explicit `ReviewDecision` records during intake, proposition inventory generation, and comparison workflows.
The method documentation includes review state as part of the core sequence.

## Decision

Human review is a first-class part of Law Proposition Extractor workflow, represented as explicit review state and review decision artifacts throughout the pipeline output.

## Consequences

Automated extraction and downstream comparison remain reviewable and can be promoted or rejected through explicit status transitions.
This introduces additional state and governance overhead but avoids treating model output as implicitly final.
