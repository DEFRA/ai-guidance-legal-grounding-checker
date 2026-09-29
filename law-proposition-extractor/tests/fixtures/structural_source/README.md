# Structural-source fixture matrix

Offline multi-instrument fixtures for Law Proposition Extractor’s structural-source fidelity
contract (hierarchy, provision numbering, legislative headings, cross-heading
safety, operative-text boundaries, extraction prompt context).

## Commands

```bash
just inspect-structural-fixtures
just check-structural-fixtures
just test-structural-fixtures
```

## Scope

- Law Proposition Extractor-only. No Proposition Matcher model/export/matching changes.
- No live legislation fetch.
- No heading-materiality classification.
- No new LLM calls.

See `docs/explainability/structural-source-fixtures.md` for the generated
human-readable report.
