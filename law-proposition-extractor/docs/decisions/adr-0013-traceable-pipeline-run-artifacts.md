# ADR-0013: Persist traceable run artifacts per pipeline execution

## Status

Accepted

## Context

Law Proposition Extractor already models run artifacts in the domain (`RunArtifact`) and includes them in pipeline bundles, but export output has been primarily flat files at the bundle root. This makes run-scoped artifact traceability weaker when multiple executions write to the same output area.

## Decision

Each pipeline export writes a run-scoped artifact directory (`runs/<run-id>/artifacts/`) with a run manifest and artifact files, while retaining existing flat root exports for compatibility.

## Consequences

Every execution has a traceable run-local artifact index and stable artifact paths that can be referenced by `storage_uri`. Existing consumers of root-level bundle files continue to work unchanged.
