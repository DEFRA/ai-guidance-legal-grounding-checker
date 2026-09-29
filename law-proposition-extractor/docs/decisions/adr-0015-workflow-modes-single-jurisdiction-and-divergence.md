# ADR-0015: Workflow modes for proposition analysis

## Status

Accepted

## Context

Pipeline behavior differs between proposition inventory runs and divergence comparison runs, and this distinction must be explicit for operators and downstream consumers.

## Decision

Law Proposition Extractor exposes two workflow modes: `single_jurisdiction` and `divergence`. The mode is persisted in `ComparisonRun.workflow_mode`, surfaced in top-level bundle/export payloads, and controls whether pairing/classification stages execute or emit explicit skip traces.

## Consequences

Run outputs are self-describing and easy to route. Single-jurisdiction runs are distinguishable without UI changes or inference from empty divergence arrays.
