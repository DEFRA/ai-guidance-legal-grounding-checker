# Guidance–law comparison — acceptance report

Date: 2026-08-03

## 1. Representative real run

**`ssafo-nitrates`** (Anna re-adjudication of Beatrice `ssafo-nitrates`)

- Already used in `ai-sdlc-content-audit` as a stakeholder/demo subject
- 217 guidance props, 3 pages, rich relationship mix, 49 multi-hit GPs, 55 only-ungrounded, 8 empty-match, 358 synthetic law-side `GUIDANCE_MISSING`

## 2. Rebuild command and output path

```bash
# Derived Matcher input (relationships unchanged; match_processing only):
#   ai-eu-trade-accelerator/runs/acceptance/ssafo-nitrates-current

cd audit-assembler
uv run audit-assembler build \
  --proposition-matcher-run ../runs/acceptance/ssafo-nitrates-current \
  --input-pair   ../../content-audit-data-assets/steps/beatrice/inputs/ssafo-nitrates-candidates \
  --relevance-filter-run ../../content-audit-data-assets/steps/radia/runs/ssafo-nvz-stub/output.json \
  --seeds        ../../content-audit-data-assets/steps/esther/seeds \
  --dest         ../../ai-sdlc-content-audit/src/server/services/audit/data \
  --category-slug ssafo-nitrates \
  --reading-age-cache ../../content-audit-data-assets-local/steps/esther/cache

uv run audit-assembler validate-guidance-comparison-contract \
  ../runs/acceptance/ssafo-nitrates-assembled
```

Assembled flat output:

- `ai-sdlc-content-audit/src/server/services/audit/data/`
- evidence copy: `ai-eu-trade-accelerator/runs/acceptance/ssafo-nitrates-assembled/`
- packed envelope: `ai-sdlc-content-audit/src/server/services/audit/runs/ssafo-nitrates/output.json`

## 3. Upstream Matcher / Adjudicator reruns

- **Matcher:** not re-run (no `ANTHROPIC_API_KEY` in env; ~$2.38 historic cost)
- **Adjudicator:** not re-run — used existing `anna/ssafo-nitrates` relationships
- **Matcher output shape:** legacy (no `match_processing`) → acceptance derived copy added only:

  `{ "candidate_count": <distinct law ids in matches[]>, "classification": "complete" }`

  Documented in `runs/acceptance/ssafo-nitrates-current/MODEL.md`. No relationships edited.

## 4. Assembled file counts

| Metric | Count |
| --- | ---: |
| Guidance propositions | 217 |
| Summaries | 217 |
| Reportable comparison pairs | 238 |
| ONLY_UNGROUNDED_CANDIDATES | 55 |
| NO_CANDIDATES_FOUND | 8 |
| NOT_CHECKED | 0 |
| PARTIAL | 0 |
| FAILED | 0 |
| INCONSISTENT (assembled) | 0 |
| Synthetic law-side GUIDANCE_MISSING rows | 358 |
| Distinct law instruments missing guidance | 2 |
| Multi-hit guidance props | 49 |

Pair relationships: GROUNDED 118, GUIDANCE_BROADER 58, GUIDANCE_INCOMPLETE 54, CONFLICTS 8.

## 5. Contract invariants

`validate-guidance-comparison-contract` → **OK**

- Summary completeness: 217 === 217
- Reportable-pair invariant: all COMPLETE + HAS_REPORTABLE match assembled pair counts
- No-pair fallback invariant: ONLY_UNGROUNDED / NO_CANDIDATES have 0 comparison rows
- Pair uniqueness: no duplicate (guidance, law) pairs
- Relationship filtering: 0 UNGROUNDED in comparisons; 1186 UNGROUNDED retained in source Matcher results
- Entity joins: all comparison GPs and law props resolve
- Legacy separation: synthetic GUIDANCE_MISSING only on `proposition-matches.json` law-side path

## 6. Real-data smoke observations

New-contract path (`usesGuidanceComparisonContract: true` for `ssafo-nitrates`):

- Overview tiles use proposition-level keys; no `UNGROUNDED` / `NO_MATCH` tiles
- Labels: Matches the law / Goes beyond the law / Only part of the law / Goes against the law / No comparable law found / No law candidate found
- Tile sum (248 excl. law-side) > total GP (217) — multi-relationship overlap confirmed
- Pages-list: status filters return distinct pages (no duplicates)
- Page-detail: multi-hit pairs rendered; fallbacks have feedback disabled
- Law-side missing guidance: separate laws href / metric
- Legacy `meadow-verdict` / `slurry`: still uses legacy path after per-category fix

## 7. Fixture-only validation

| Scenario | Real data | Fixture / unit |
| --- | --- | --- |
| A Grounded | yes | yes |
| B Multi-hit | yes (49) | yes |
| C Grounded + ungrounded | yes (reportable shown, UNGROUNDED hidden) | yes |
| D Only ungrounded | yes (55) | yes |
| E No candidates | yes (8) | yes |
| F Not checked | no (derived COMPLETE) | yes |
| G Partial | no | yes |
| H Failed | no | yes |
| I Inconsistent | no | yes (deliberate fixture) |
| J Guidance broader | yes | yes |
| K Conflict | yes | yes |
| L Law-side missing | yes | yes |
| M Legacy run | yes (`meadow-verdict`) | yes |

## 8. Route-level tests added

- `ai-sdlc-content-audit/test/unit/server/features/audit-guidance-comparison-routes.smoke.test.js` (7)
- `ai-sdlc-content-audit/test/integration/guidance-comparison-ssafo.smoke.test.js` (4)

## 9. Files changed

**ai-eu-trade-accelerator**

- `audit-assembler/src/audit_assembler/validate_guidance_comparison.py` (new)
- `audit-assembler/src/audit_assembler/cli.py` (`validate-guidance-comparison-contract`)
- `audit-assembler/tests/test_validate_guidance_comparison.py` (new)
- `audit-assembler/README.md`
- `runs/acceptance/ssafo-nitrates-current/` (derived Matcher input)
- `runs/acceptance/ssafo-nitrates-assembled/` (assembled evidence)
- `runs/acceptance/ACCEPTANCE-REPORT.md` (this file)

**ai-sdlc-content-audit**

- `src/server/services/audit/create-audit-service.js` — **per-category** contract gate (acceptance fix)
- `src/server/services/audit/guidance-comparison.md`
- `src/server/services/audit/data/*` (rebuilt)
- `src/server/services/audit/runs/ssafo-nitrates/output.json` + `MODEL.md`
- route/integration smoke tests (above)

**content-audit-data-assets** (partial)

- `steps/esther/scripts/pack-run.mjs` — optional new presentation files

## 10. Commands run

```text
uv run audit-assembler build …   # see §2
uv run audit-assembler validate-guidance-comparison-contract …
cd audit-assembler && uv run pytest -q
cd proposition-matcher && uv run pytest -q
cd match-adjudicator && uv run pytest -q
cd ai-sdlc-content-audit && npm test
cd ai-sdlc-content-audit && npx vitest run test/unit/server/features/audit-guidance-comparison-routes.smoke.test.js test/integration/guidance-comparison-ssafo.smoke.test.js
```

## 11. Test results by package

| Package | Command | Result |
| --- | --- | --- |
| proposition-matcher | `uv run pytest -q` | 35 passed |
| match-adjudicator | `uv run pytest -q` | 5 passed |
| audit-assembler | `uv run pytest -q` | 40 passed |
| ai-sdlc-content-audit | `npm test` | 25 files / 124 passed |
| ai-sdlc-content-audit smoke (new) | vitest focused | 11 passed |

No suites skipped. Law-proposition-extractor / discovery not in scope.

## 12. Original acceptance criteria mapping

| Ticket requirement | Result |
| --- | --- |
| Unchecked → Not yet compared (not “no candidate”) | **Pass** (fixture F; contract forbids empty-matches⇒NO_CANDIDATES without processing) |
| No candidate vs all rejected | **Pass** real data: 8 / 55 with distinct labels |
| Multiple hits displayed; overview proposition-based | **Pass** real data (49 multi-hit; tile overlap) |
| Grounded relationships displayed | **Pass** — project terms: GROUNDED / GUIDANCE_BROADER / GUIDANCE_INCOMPLETE / CONFLICTS with UI labels Matches the law / Goes beyond the law / Only part of the law / Goes against the law. Ticket `GROUNDED_BROADER` ≠ project `GUIDANCE_BROADER`. |

## 13. Legacy-run compatibility

- `meadow-verdict` / category `slurry` remains on legacy path when summaries absent for that category
- **Defect found & fixed:** global `hasGuidanceComparisonContract()` previously forced new path on all categories once any run had summaries → meadow page-detail became `INCONSISTENT_DATA` / broke feedback integration tests
- Fix: per-category contract detection in `create-audit-service.js`

## 14. Product confirmation items (non-blocking)

1. **Multi-relationship membership** — one GP may appear in every applicable relationship tile; totals must not be summed from tiles (observed: 248 tile memberships vs 217 GPs).
2. **Historic Matcher backfill** — production rebuilds of pre-`match_processing` runs need either a Matcher re-run or an official reconstruction policy (this acceptance used an explicit derived copy).

## 15. Remaining defects

None blocking. Optional hygiene:

- Assembler warnings on ssafo rebuild: 500 law props lack legacy seed enrichment; 3 pages missing relevance scores (null) — pre-existing data gaps, not comparison-contract failures.
- Packing rebuilt envelope into `content-audit-data-assets/steps/esther/runs/` was not completed (cross-repo write gated).

---

```text
ACCEPT WITH FOLLOW-UP — core ticket requirements are satisfied; list non-blocking follow-ups.
```

Follow-ups:

1. Persist real `match_processing` via Matcher re-run for production historic runs.
   Official policy `historic_match_processing_backfill_v1` is implemented
   (`proposition-matcher backfill-match-processing`) but Beatrice `ssafo-nitrates`
   is **not** eligible under it: metrics `guidance_props_empty: 2` vs 8 empty
   `matches[]` rows, no `survivors.json`, and `candidate_count` must not be
   inferred from `matches[]`. The acceptance copy remains acceptance-only
   (see `ssafo-nitrates-current/MODEL.md`).
2. Product confirm multi-relationship tile overlap semantics.
3. Optionally sync packed `ssafo-nitrates` envelope into `content-audit-data-assets`.
