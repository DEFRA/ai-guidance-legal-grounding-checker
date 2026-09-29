# Match Adjudicator

Match Adjudicator sits between **Proposition Matcher** and **Audit Assembler**. Proposition Matcher classifies each guidance
proposition against the law one pair at a time, so it over-reports gaps and
conflicts — the resolving text is usually in a *sibling* proposition on the same
page that Proposition Matcher's per-pair view never sees. Match Adjudicator re-reads each flagged finding
with the whole page's guidance plus Proposition Matcher's stated reason, and decides whether
the verdict still holds.

By the time the corpus reaches Match Adjudicator it has narrowed to the flagged findings only
(`CONFLICTS` + `GUIDANCE_INCOMPLETE`), so it can afford this wider, more expensive
second look.

## What it does

- Reads Proposition Matcher's `results.json` (guidance propositions, each with a best-first
  `matches` list; the match's law text lives in `law_proposition`).
- For every **top match** (the one Audit Assembler surfaces) whose relationship is
  `CONFLICTS` or `GUIDANCE_INCOMPLETE`, re-adjudicates it against the other
  guidance propositions on the same page (`url`) plus Proposition Matcher's reason for the
  verdict.
- All flagged findings are judged in **one Anthropic Message Batch** (50% cost).
- **Commits the decision**: the finding either stays flagged or becomes
  `GROUNDED`. There is no "maybe" — the corrected status is what comes out.

## Output shape — a drop-in for Audit Assembler

Match Adjudicator writes a run in **Proposition Matcher's own shape**, so Audit Assembler consumes it unchanged:

```
match-adjudicator/runs/<name>/
  results.json       # Proposition Matcher schema; top-match relationship + explanation corrected in place
  match_adjudicator_report.json   # audit trail: every change (old -> new status, both reasons). Not in the pipeline path.
  metrics.json
  MODEL.md
```

`results.json` carries no extra fields and no review flags — it is exactly what
Proposition Matcher would have produced had it judged with page context. Audit Assembler reads
`matches[0]` as before:

```bash
audit-assembler build --proposition-matcher-run ../match-adjudicator/runs/<name> --input-pair … --relevance-filter-run … --seeds … --dest …
```

The full audit (what Match Adjudicator changed and why) lives in `match_adjudicator_report.json`, outside
the pipeline, for humans and debugging.

## Usage

```bash
uv sync
export ANTHROPIC_API_KEY=sk-...

DATA=../../content-audit-data-assets/steps
uv run match-adjudicator readjudicate \
  --proposition-matcher-run $DATA/proposition-matcher/runs/heron-verdict \
  --dest         $DATA/match-adjudicator/runs/heron-verdict \
  --model        claude-sonnet-4-6 \
  --dry-run
```

`--dry-run` counts the flagged findings the batch would judge and stops before any
API spend. Drop it to submit the batch and write the run (`--poll-seconds` tunes
the batch poll interval, default 30). Then point Audit Assembler's `--proposition-matcher-run` at the
Match Adjudicator run instead of the Proposition Matcher run.

## Tests

```bash
uv run pytest        # pure transform, no network (a stub judge stands in for the LLM)
```

## Provenance

The re-adjudication prompt is the shipped v5 from the Match Adjudicator benchmark
(`draft-pipelines/match-adjudicator/`): brief instruction + Proposition Matcher's reason + a page-context
coverage check and a light subject-match note. The benchmark established that on
the labelled feedback set it clears the false positives Proposition Matcher raised while
holding the genuine findings, and that prompt length / model tier moved results
only within the eval's own noise band — so Match Adjudicator ships on `claude-sonnet-4-6`.
