# Live proposition calibration

Evaluation-only measurement of Law Proposition Extractor **prompt v3 + configured frontier model**
against the proposition-fidelity gold contracts.

## Offline benchmark vs live calibration

| Contract | Question |
| --- | --- |
| Offline proposition-fidelity benchmark | Do curated extraction responses survive validation/reconciliation into faithful propositions? |
| Live proposition calibration | Does the current frontier model, given prompt v3, produce extraction responses that survive the same path? |

The offline benchmark remains the stable deterministic regression contract.
Live calibration does **not** overwrite `tests/fixtures/proposition_fidelity/**`.

## Latest calibration

- **Date / run id:** `live-pf-20260715T155907Z`
- **Timestamp:** `2026-07-15T16:01:20.154671+00:00`
- **Model alias:** `frontier_extract`
- **Resolved provider/model:** `anthropic/claude-sonnet-4-5-20250929`
- **Prompt version:** `v3`
- **Request parameters:** temperature=`0.0`, seed=`None`
- **Case matrix:** `article_49a`, `uk_regulation_12_spread`, `wsi_regulation_36_4`
- **Repetitions:** 3 per case (9 case-repetitions)
- **Provider calls:** `15` (retries: `0`)
- **Artifacts:** `calibration/proposition_fidelity/live-pf-20260715T155907Z/`

## Pass/fail summary

- critical failures: 12
- warnings: 6

## Semantic stability

- `article_49a`: consistently_failing (fidelity=fail, repeatability=pass)
- `uk_regulation_12_spread`: consistently_failing (fidelity=fail, repeatability=pass)
- `wsi_regulation_36_4`: semantically_stable (fidelity=pass, repeatability=pass)

## Promotion status

No automatic fixture promotion. Candidates (if any) are listed in the run report only.

## Historical result vs current-code recheck

The live calibration artifacts are an immutable historical record of what the
frontier model produced under the code and evaluator **at run time**.

A separate offline command can replay the exact saved raw responses through
**current** deterministic production code and the corrected
proposition-fidelity evaluator:

```bash
just recheck-live-proposition-calibration live-pf-20260715T155907Z
```

That writes only:

- `calibration/proposition_fidelity/<run-id>/current_code_recheck.json`
- `calibration/proposition_fidelity/<run-id>/current_code_recheck.md`

It does **not** overwrite `calibration_result.json`, `calibration_report.md`,
or saved `calls/*.json`. It makes no model or network calls.

For `live-pf-20260715T155907Z`, the current-code recheck measures the combined
effect of:

- `relationship.infer_triggered_by` v2 (Article 49a `triggered_by`)
- `extraction.suppress_dependent_qualification` v1 (UK regulation 12)
- structured `action_expectation` action fidelity (Article 49a P2)

Completeness warnings (`context_dependent` vs `complete`) may remain and are
intentionally deferred.

## Limitations

- External model behaviour can change without notice.
- Article 49a production path issues three fragment calls per repetition.
- This page records one calibration event; re-run to refresh.
- Current-code recheck is not a new model calibration; it only measures current
  deterministic code against saved responses.

## Commands

```bash
just run-live-proposition-calibration
just inspect-live-proposition-calibration <run-id>
just check-live-proposition-calibration <run-id>
just recheck-live-proposition-calibration <run-id>
just replay-live-article-49a-relationships <run-id>
just replay-live-uk-regulation-12 <run-id>
```

Live run requires model credentials and network. Inspect/check/recheck/replay
are offline.

