# ADR-0018: Proposition identity and naming

## Status

Accepted

## Context

Propositions are referenced across extraction, inventory, operational history, comparison, and UI. Mixing durable identity, source lineage, human-readable names, and routing handles leads to brittle exports and ambiguous analytics. Legal-area labels, categories, and interpretive tags must remain separate from stable machine identity.

## Decision

Law Proposition Extractor separates **machine identity**, **source-derived lineage keys**, **human-readable naming**, and **UI routing slugs**.

1. **`Proposition.id`** is an opaque, stable machine identifier.

   - It must not encode legal area, category, conclusion, or transient interpretation.
   - It should be deterministic where possible (structural basis: source record, fragment anchor, extraction sequence token).
   - It should remain stable across pipeline reruns when the same structural proposition is recognised.

2. **`Proposition.proposition_key`** is a **source-derived lineage key**, not durable identity.

   - Preferred format: `<instrument-id>:<fragment-locator>:pNNN` (three colon-separated segments; final segment is a zero-padded proposition ordinal within that source anchor).
   - Examples: `eur-2016-429:art-109:p001`, `retained-2016-429:art-109:p001`, `uk-si-2019-xxx:reg-12:p001`.
   - Callers may supply an explicit `proposition_key` when importing curated data; otherwise the pipeline derives it from registered source metadata.

3. **`Proposition.label`** is human-readable.

   - Intended format: `<source locator> — <short legal proposition name>` (em dash separator).
   - Example: `Article 109 — habitual establishment requirement`.

4. **`Proposition.short_name`** is a compact display title (often derived from subject and action when not provided).

5. **`Proposition.slug`** is for UI routing and list views only.

   - It may be generated from `label`.
   - It must not be treated as durable identity or used for lineage joins.

6. **Legal-area / category tags** must never be baked into **`Proposition.id`** (or substituted for it in APIs that require stable references).

   - Bad: `equine-movement-art109-001` as machine id.
   - Good: opaque `id`, source lineage in `proposition_key`, readable text in `label` / `short_name`, canonical type in `proposition_tier` / `legal_effect_type`, legacy LLM tags in `categories` / heuristic tags in `tags`.

## Consequences

- Export bundles and operational history should key stable joins on `id` (and version fields where applicable), lineage on `proposition_key`, and presentation on `label` / `short_name` / `slug`.
- Renderers and operators must not treat `slug` or `proposition_key` as substitutes for `id`.
- Older run artifacts may still carry legacy `proposition_key` strings; consumers should tolerate both historical and ADR-shaped keys where exact string equality across tool versions is not required.

## Related

- ADR-0006: proposition as analysis unit.
- ADR-0009: source provenance and snapshot references for lineage.
- ADR-0014: proposition-first architecture.
- ADR-0016: compatibility policy for proposition migration.
