# Method

Law Proposition Extractor analyzes structured legal propositions, not just document text.

The workflow is:

1. build a source register
2. extract propositions
3. enrich proposition inventory (categories, tags, cross-reference structure, review state; opaque `id`, source-derived `proposition_key`, and display labels per ADR-0018)
4. optionally compare propositions across jurisdictions for divergence
5. export structured and narrative outputs

![Method core workflow](../assets/generated/diagrams/core-workflow.svg)

*Figure: Method flow from authoritative sources through SourceRecord/SourceSnapshot/SourceFragment into proposition extraction and Proposition inventory, with reviewable context and optional downstream divergence outputs.*

Generated assets may be absent in a clean checkout. Run `just docs-refresh` to regenerate them.
