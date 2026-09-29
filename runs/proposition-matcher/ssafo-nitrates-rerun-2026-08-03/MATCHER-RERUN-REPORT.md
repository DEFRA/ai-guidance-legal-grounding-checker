# Matcher rerun reconciliation — ssafo-nitrates

Generated: `2026-08-03T18:44:16`

## Paths

- **new_run:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/runs/proposition-matcher/ssafo-nitrates-rerun-2026-08-03`
- **beatrice:** `/Users/bram/Code/defra/content-audit-data-assets/steps/beatrice/runs/ssafo-nitrates/results.json`
- **anna:** `/Users/bram/Code/defra/content-audit-data-assets/steps/anna/runs/ssafo-nitrates/results.json`
- **acceptance:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/runs/acceptance/ssafo-nitrates-current/results.json`

## Validation gate

- ok: `True`
- ready_for_adjudication: `False`
- classifications: `{'complete': 208, 'failed': 7, 'partial': 2}`
- candidate_count mismatches: `0`

## Run summary

| Metric | Historic Beatrice | Anna adjudicated | Acceptance-derived | New Matcher |
| --- | ---: | ---: | ---: | ---: |
| Guidance propositions | 217 | 217 | 217 | 217 |
| Native processing records | 0 | 0 | 217 | 217 |
| Complete | 0 | 0 | 217 | 208 |
| Failed | 0 | 0 | 0 | 7 |
| Partial | 0 | 0 | 0 | 2 |
| Not attempted | 0 | 0 | 0 | 0 |
| Zero survivors | 0 | 0 | 8 | 2 |
| Empty matches[] rows | 8 | 8 | 8 | 9 |
| Pair rows | 1424 | 1424 | 1424 | 1399 |
| Distinct pairs | 1424 | 1424 | 1424 | 1399 |
| Multi-hit guidance propositions | 49 | 49 | 49 | 49 |
| Only-ungrounded guidance propositions | 55 | 55 | 55 | 52 |
| Reportable pair rows | 238 | 238 | 238 | 233 |

## Relationship distribution

| Relationship | Historic Beatrice | Anna adjudicated | Acceptance-derived | New Matcher |
| --- | ---: | ---: | ---: | ---: |
| GROUNDED | 98 | 118 | 118 | 96 |
| UNGROUNDED | 1186 | 1186 | 1186 | 1166 |
| CONFLICTS | 11 | 8 | 8 | 8 |
| GUIDANCE_INCOMPLETE | 71 | 54 | 54 | 71 |
| GUIDANCE_BROADER | 58 | 58 | 58 | 58 |
| GUIDANCE_MISSING | 0 | 0 | 0 | 0 |

## A. Historic Beatrice vs new Matcher — pair churn

- Unchanged distinct pairs: **1367**
- New pairs: **32**
- Removed pairs: **57**
- Same pair, changed raw relationship: **81**
- Changed top pairs: **34**

## B. Anna adjudicated vs new Matcher — portability

Anna is adjudicated; the new run is raw Matcher output. **Do not treat portability as auto-apply permission.**

- Historic adjudications (Anna≠Beatrice top): **20**
- Portability counts: `{'UNCHANGED_PAIR_PRESENT': 3, 'PAIR_PRESENT_RELATIONSHIP_DIFFERS': 17}`
- Safe to review on same pair: **17**
- Historic adjudicated pair disappeared: **0**
- Adjudication now non-top / would hit different rank: **3**
- Raw Matcher already agrees with Anna on adjudicated pair: **3**
- Blind copy would change a different pair: **3**
- Propositions needing fresh adjudication: **17**

## C. Acceptance-only derived vs new Matcher

Acceptance copy reconstructed candidate_count from distinct law IDs in matches[] and forced classification=complete. It is not authoritative production Matcher evidence.

- Candidate-count differences: **7**
- Only-ungrounded: acceptance=55, new=52
- Zero survivors: acceptance=8, new=2
- Reportable pairs: acceptance=238, new=233
- Multi-hit guidance: acceptance=49, new=49

## Adjudication recommendation

**FULL_ADJUDICATOR_RERUN_REQUIRED**

Reasons:
- native run is not ready for adjudication (incomplete processing)

This increment does not implement the recommendation.

## Incomplete propositions (blocks adjudication)

Native processing is present for all 217 guidance propositions, but **9 are not complete**.

| Guidance proposition ID | Classification | Failure reason | Survivors | Match rows |
| --- | --- | --- | ---: | ---: |
| `susan-41dbc58cc6ea1113-14` | failed | `group_rerank_parse_failed` | 15 | 0 |
| `susan-41dbc58cc6ea1113-15` | failed | `group_rerank_parse_failed` | 15 | 0 |
| `susan-41dbc58cc6ea1113-16` | failed | `group_rerank_parse_failed` | 15 | 0 |
| `susan-41dbc58cc6ea1113-17` | failed | `group_rerank_parse_failed` | 15 | 0 |
| `susan-41dbc58cc6ea1113-40` | failed | `group_rerank_parse_failed` | 14 | 0 |
| `susan-41dbc58cc6ea1113-58` | partial | `not_all_candidates_classified` | 14 | 13 |
| `susan-41dbc58cc6ea1113-63` | failed | `group_rerank_parse_failed` | 15 | 0 |
| `susan-b5cccee08ec65fb7-7` | partial | `not_all_candidates_classified` | 15 | 14 |
| `susan-b5cccee08ec65fb7-79` | failed | `group_rerank_parse_failed` | 11 | 0 |

7 group_rerank_parse_failed rows had candidate_count 11–15; CLASSIFY_MAX_TOKENS=2048 may truncate large group-rerank JSON. No config change made in this increment.

Batch API request errors: group-rerank errored=0, summarise errored=0. Failures are parse / partial-classification outcomes, not transport errors.

## Operational provenance

- **Command:** `uv run proposition-matcher run --guidance /Users/bram/Code/defra/content-audit-data-assets/steps/susan/runs/ssafo-nvz-3/output.json --law /Users/bram/Code/defra/content-audit-data-assets/steps/judit/runs/ssafo-nitrates-2-export/beatrice_law_candidates.json --law-source candidates --out /Users/bram/Code/defra/ai-eu-trade-accelerator/runs/proposition-matcher/ssafo-nitrates-rerun-2026-08-03`
- **Started (UTC):** `2026-08-03T17:28:43Z`
- **Completed (UTC):** `2026-08-03T17:43:21Z`
- **Model:** `claude-sonnet-4-6` (alias `claude-sonnet-4-6`)
- **Embed:** `nomic-embed-text:v1.5`
- **Retrieval:** top_k=15, threshold=0.65, score_gap=0.04
- **Cache:** no cross-run pipeline cache; Anthropic `cache_read` tokens = 0 / 0
- **Batches:** group-rerank `msgbatch_01TdrhR4R3oB1KA7aPZkSWgC`; summarise `msgbatch_01GEKbLJ6veuWshA5Q5ytfcR`
- **Cost / tokens:** $2.4021 ; in=519019, out=216471
- **Input SHA256:** guidance `3e6582fe693658e7c928c2138ab328e195c5b2b2545869b60ef69ff2c1e1ae10`; law `1c06b1d02173c5e707ad5fd995f63d739704b15ba5bc4705725781bd06c87317`
- **Results SHA256:** `4ab096d1c029650e3c4f951350560207d2f515a1389c48047f3f5352feb91637`
- **Git:** ai-eu-trade-accelerator `a32aa99224ae749772efc1710e326fdb0f28d81f`; content-audit-data-assets `187dab170767feff8dece9317f8f3961c7140b65`

## Status

**MATCHER RERUN INCOMPLETE** — resolve the 9 non-complete propositions before adjudication.

### Next increment (suggested)

Re-run the established production Matcher command to a **new** immutable directory (do not overwrite this diagnostic run). Example:

```bash
cd /Users/bram/Code/defra/ai-eu-trade-accelerator/proposition-matcher
set -a && source .env && set +a
uv run proposition-matcher run \
  --guidance /Users/bram/Code/defra/content-audit-data-assets/steps/susan/runs/ssafo-nvz-3/output.json \
  --law /Users/bram/Code/defra/content-audit-data-assets/steps/judit/runs/ssafo-nitrates-2-export/beatrice_law_candidates.json \
  --law-source candidates \
  --out /Users/bram/Code/defra/ai-eu-trade-accelerator/runs/proposition-matcher/ssafo-nitrates-rerun-2026-08-03-retry
```

Then:

```bash
uv run proposition-matcher validate-run \
  --run .../ssafo-nitrates-rerun-2026-08-03-retry \
  --guidance .../susan/runs/ssafo-nvz-3/output.json \
  --law .../beatrice_law_candidates.json \
  --law-source candidates \
  --write-json .../native-run-validation.json

uv run proposition-matcher reconcile-rerun \
  --new-run .../ssafo-nitrates-rerun-2026-08-03-retry \
  --beatrice .../beatrice/runs/ssafo-nitrates \
  --anna .../anna/runs/ssafo-nitrates \
  --acceptance .../runs/acceptance/ssafo-nitrates-current \
  --validation-json .../native-run-validation.json
```

If that retry is fully complete, current churn evidence suggests **PAIRWISE_ADJUDICATION_RECONCILIATION_POSSIBLE** (0 Anna pairs disappeared; exact-pair join still works). Do not auto-apply Anna.

Do **not** run Match Adjudicator or Audit Assembler until validate-run reports `ready_for_adjudication=True`.
