# Acceptance-derived Matcher run — ssafo-nitrates-current

## Purpose

Acceptance rebuild input for the guidance–law comparison contract.

## Source

- **Unmodified relationships from:** `content-audit-data-assets/steps/anna/runs/ssafo-nitrates/results.json`
- **Upstream Beatrice run:** `beatrice/runs/ssafo-nitrates` (completed group-rerank; 0 errored)

## Derivation (explicit, not a silent edit of the source)

Legacy Anna/Beatrice `results.json` predates `match_processing`. Current Audit Assembler
requires that field to emit `COMPLETE` coverage / reportable comparisons; without it every
proposition becomes `NOT_CHECKED` and multi-hit rows are suppressed.

This copy **only adds** per-row:

```json
{ "candidate_count": <distinct law ids in matches[]>, "classification": "complete" }
```

No `relationship` values were changed. No synthetic matches were added or removed.
`match_summary` is not written (Assembler re-derives).

## Why this is not manufacturing states

Pair outcomes remain Anna's. Processing metadata records that this completed run did classify
the survivors present on each row — consistent with Beatrice metrics (`errored: 0`).
EMPTY `matches` → `candidate_count: 0` → Assembler `NO_CANDIDATES_FOUND`.

## Not the production backfill policy

This acceptance copy is **acceptance-only**. It is **not**
`historic_match_processing_backfill_v1`.

The official production policy (Proposition Matcher
`backfill-match-processing`) refuses to infer `candidate_count` from
`len(matches)` / distinct law IDs and refuses to treat empty `matches[]` as
`NO_CANDIDATES_FOUND` without affirmative survivor or metrics-alignment
evidence. Beatrice `ssafo-nitrates` metrics report `guidance_props_empty: 2`
while results contain 8 empty-match rows and no survivors artefact — so under
the official policy the historic run is **not** production-backfill eligible
and needs a Matcher rerun (or recovered per-proposition evidence).
