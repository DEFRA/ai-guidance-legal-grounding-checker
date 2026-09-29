# ADR-0005: Adopt source-first ingestion through a source register

## Status

Accepted

## Context

The pipeline entrypoint requires case files with a non-empty `sources` array and starts by registering source records, snapshots, and fragments before any extraction or comparison. There is no upload workflow or upload API in the current architecture.

## Decision

Law Proposition Extractor v1 uses source-first ingestion: all analysis begins from explicit source records (with jurisdiction, citation, and text) that are registered before proposition extraction.

## Consequences

Pipeline runs are reproducible from structured source input and keep a clear provenance chain from source to assessment. Ad-hoc upload-first UX is out of scope for v1 and must be added as a separate ingestion path later.
