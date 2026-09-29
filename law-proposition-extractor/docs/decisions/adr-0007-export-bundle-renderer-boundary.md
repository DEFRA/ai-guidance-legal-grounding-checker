# ADR-0007: Treat the static export bundle as a first-class boundary

## Status

Accepted

## Context

The architecture and pipeline explicitly model a validated export bundle boundary, with exporters writing a stable set of JSON/Markdown artifacts. Future Astro rendering is documented as consuming this bundle without owning business logic.

## Decision

The export bundle is a first-class contract between analysis logic and presentation layers, including future static renderers.

## Consequences

Renderer technology can evolve independently from pipeline/domain logic as long as bundle compatibility is maintained. Changes to bundle schema become architectural changes that require deliberate versioning and migration strategy.

Proposition records in the bundle expose opaque `id`, source-derived `proposition_key`, and display fields (`label`, `short_name`, `slug`) per ADR-0018; renderers must not treat `slug` or `proposition_key` as durable identity.
