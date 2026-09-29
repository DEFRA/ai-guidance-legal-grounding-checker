# Historic `match_processing` backfill policy

Policy version: **`historic_match_processing_backfill_v1`**

Fail-closed reconstruction of Matcher `match_processing` for historic runs that
predate the field. Owned by **Proposition Matcher**. Audit Assembler consumes
approved metadata only and never invents processing state.

## Why empty `matches[]` is insufficient

A historic empty `matches[]` row may mean:

- candidate discovery completed with zero survivors;
- classification completed and every candidate was filtered/omitted;
- the proposition was never attempted;
- an LLM/parse failure;
- partial processing;
- a lost or omitted result.

Live Matcher runs resolve this with explicit `match_processing`. Without
affirmative evidence, reconstructing `complete` + `candidate_count: 0` would
falsely unlock `NO_CANDIDATES_FOUND` in the guidance-comparison contract.

## Authoritative artefacts

| Artefact | Role |
|---|---|
| `results.json` / `output.json` | Result rows, pair relationships (preserved verbatim) |
| `survivors.json` | **Authoritative group-rerank survivor law IDs** → `candidate_count` (`{gp_id: [law_id, …]}`) |
| `intermediates/04-matches.json` | **Not authoritative** for v1 — older dumps can be broader retrieval lists, not the group-rerank survivor set |
| `metrics.json` | Run-level counters; usable only under narrow alignment rules |
| `proposition_errors.json` | Per-proposition terminal failures |
| `proposition_skips.json` | Explicit not-attempted / skip set |
| `guidance_proposition_ids.json` | Optional in-scope identity list |
| `MODEL.md` | Human provenance only — not sufficient alone for machine classification |

## Semantic definition of `candidate_count`

Identical to live Matcher runs: **number of retrieval survivors** after cosine
threshold + `score_gap` + `top_k` (see `matching/embeddings.py` /
`pipeline/batch_match.py`).

It is **not**:

- `len(matches)`
- distinct law IDs in `matches[]`
- reportable-pair count

Inferring count from `matches[]` is forbidden unless a survivors artefact proves
the same set.

## Classification rules

### Native

If a row already has valid `match_processing`, preserve it unchanged. Do not
overwrite. Analysis marks `native`.

### `complete`

Only when artefacts prove all Matcher stages intended for that guidance
proposition completed successfully:

1. **Survivors artefact present** and every survivor law ID appears in the
   result `matches[]` (or survivors length is 0); or
2. **Metrics empty-count alignment** (narrow):  
   `guidance_props_empty + guidance_props_with_survivors == guidance_propositions == len(results)`,  
   `group_rerank.errored == 0`, and `count(empty matches) == guidance_props_empty`  
   — then **empty-match rows only** may be `complete` with `candidate_count: 0`.

Non-empty `matches[]` without a survivors artefact is **not** automatically
`complete`.

### `failed`

Per-proposition terminal failure in `proposition_errors.json` (stable
`failure_reason` code only — no prompts/stack traces).

### `partial`

Survivors artefact shows some but not all survivors classified into `matches[]`
(`not_all_candidates_classified` / `no_candidates_classified`).

### `not_attempted`

Only with an explicit skip record in `proposition_skips.json`.

### Ambiguous

Anything else — including empty matches without alignment, non-empty matches
without survivors, missing rows without skips, and run-level
`group_rerank.errored > 0` without per-proposition attribution.

Ambiguity is a **migration/report** status (`AMBIGUOUS_FOR_BACKFILL` in the
analysis report). It is **not** added to the runtime `classification` enum.

## Run eligibility

A run is production-backfill eligible only when every in-scope guidance
proposition has either:

- valid native `match_processing`, or
- a record reconstructed under this policy.

If any proposition is ambiguous or has invalid native processing:

- do **not** emit a production-ready derived run;
- leave the original run on the legacy frontend path;
- require a Matcher rerun or richer source evidence.

## CLI

```bash
# Analysis (no writes). Exit 0 if eligible, 2 if not.
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-matcher-run \
  --check

# Optional machine report
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-matcher-run \
  --check \
  --report-json /tmp/backfill-report.json

# Write derived run (refuses if not eligible; never mutates source)
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-matcher-run \
  --dest path/to/derived-run

# Replace an existing destination explicitly
uv run proposition-matcher backfill-match-processing \
  --run path/to/historic-matcher-run \
  --dest path/to/derived-run \
  --overwrite
```

### Derived-run contract

- Preserves all source result data, pair relationships, ordering, explanations,
  confidence, and match IDs.
- Adds only approved `match_processing` (+ re-derived `match_summary`) and
  provenance.
- Writes `match_processing_backfill_report.json` and appends a MODEL.md note.
- Atomic directory publish (temp dir + rename).
- Idempotent for the same source + policy (no timestamps in processing records).

### Provenance shape (reconstructed rows)

```json
{
  "candidate_count": 4,
  "classification": "complete",
  "provenance": {
    "origin": "historic_backfill",
    "policy_version": "historic_match_processing_backfill_v1",
    "evidence_codes": [
      "RESULT_ROW_PRESENT",
      "SURVIVOR_LIST_PRESENT",
      "ALL_SURVIVORS_CLASSIFIED",
      "CANDIDATE_COUNT_FROM_SURVIVOR_LIST"
    ],
    "source_run": "/abs/path/to/source",
    "source_content_hash": "sha256:…",
    "tool_version": "0.1.0"
  }
}
```

## Operational sequence

```text
analyse historic run (--check)
→ review ambiguity report
→ backfill only if eligible (--dest)
→ validate reconstructed metadata
→ run Audit Assembler
→ validate guidance comparison contract
→ pack/deploy rebuilt presentation data
```

```bash
uv run audit-assembler build \
  --proposition-matcher-run path/to/derived-run \
  …

uv run audit-assembler validate-guidance-comparison-contract \
  path/to/assembled
```

## When a real Matcher rerun is mandatory

- No `survivors.json` **and** metrics empty-count alignment fails
  (including runs that only have older `intermediates/04-matches.json` retrieval dumps).
- `group_rerank.errored > 0` without per-proposition error attribution.
- Any in-scope proposition remains ambiguous under this policy.
- You need authoritative survivor counts that were never persisted.

## Audit Assembler boundary

- Consumes valid native or approved reconstructed `match_processing`.
- Does **not** reconstruct historic processing.
- Absent metadata → `NOT_CHECKED` (legacy path).
- Rejects `provenance.origin == historic_backfill` with unknown/missing
  `policy_version` or empty `evidence_codes`.
- Emits a diagnostic warning when approved historic_backfill rows are present.

## Acceptance copy caveat

`runs/acceptance/ssafo-nitrates-current/` marked every historic row
`classification: complete` with `candidate_count = distinct law IDs in matches[]`.

That was an **acceptance-specific derivation**, not this production policy.
It remains useful as acceptance evidence but is **not** an approved production
backfill unless the original historic artefacts independently pass
`historic_match_processing_backfill_v1`.

For Beatrice `ssafo-nitrates`, metrics report `guidance_props_empty: 2` while
`results.json` has **8** empty `matches[]` rows, and no survivors artefact is
present — so under this policy the run is **not** production-backfill eligible
and requires a Matcher rerun (or recovery of per-proposition survivor / batch
evidence).
