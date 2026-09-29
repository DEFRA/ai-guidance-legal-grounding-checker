# Baseline replay (AC-10)

Deterministic before/after comparison for the component rename.

## Method

1. **Before rename** — capture fingerprints from fixed inputs (slurry example artifacts /
   fixtures) without re-calling live models where possible.
2. **After rename** — re-run the same fingerprint script against the renamed tree.
3. Diff may only change the allowlisted identity surfaces listed below.

## Allowlisted deltas

- component display names and slugs
- command / package / module paths
- producer labels and MODEL.md titles
- log and metrics display labels
- documentation-facing identifiers
- handoff filenames that gained dual-read aliases

## Must remain equivalent

- proposition IDs (including `susan-…`, `prop:…`)
- proposition content and counts
- source references and evidence
- proposition relationships
- candidate retrieval results
- classifications, scores and verdicts
- item ordering
- audit structure
- frontend-visible substantive conclusions

## Captured baseline

See [`fingerprints.json`](fingerprints.json) produced by
`scripts/capture_replay_fingerprints.py`.
