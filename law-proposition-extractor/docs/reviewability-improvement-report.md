# Reviewability improvement report

**Date:** 2026-06-12
**Corpus:** Slurry GB principal-5
**Before:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export-json-repaired` (Previous export (279-fragment intake, json-repaired extraction))
**After:** `/Users/bram/Code/defra/ai-eu-trade-accelerator/law-proposition-extractor/runs/slurry-gb-principal-5-current-export` (Regenerated export (727-fragment intake, frontier extraction))

This report measures whether structural source-fidelity improvements measurably improved a human reviewer's ability to assess Law Proposition Extractor outputs. It does **not** judge legal correctness.

## Executive summary

- Statements: **730** → **1415** (+685).
- Workbench exact internal context resolutions: **106** → **258** (+152).
- Workbench unresolved context references: **11** → **45**; unresolved rate **5.6%** → **7.3%**.
- Partial → exact shift: workbench partial resolutions **52** → **0**; exact **106** → **258**.
- Statements previously blocked by unresolved context, now reviewable (matched by text): **0**; workbench-unresolved → fully resolved: **0**.
- Corrupt source fragments: **146** → **118**; corrupt evidence quotes: **161** → **144**.

## 1. Statement counts

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Effective law statements | 730 | 1415 | 685 |
| Guidance matching candidates | 591 | 1070 | 479 |
| `partially_resolved` statements | 129 | 245 | 116 |
| `context_dependent` statements | 39 | 413 | 374 |
| Propositions | 730 | 1415 | 685 |
| Source fragments | 279 | 727 | 448 |

## 2. Context resolution

### 2.1 Export metadata (`required_context.resolution_status`)

| Status | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Unresolved | 86 | 299 | 213 |
| Resolved | 49 | 167 | 118 |
| External reference | 27 | 37 | 10 |
| Ambiguous | 72 | 180 | 108 |
| Statements with `standalone_status: partially_resolved` | 129 | 245 | 116 |
| Statements with any required context | 197 | 523 | 326 |

Absolute unresolved counts rise with corpus size (2× statements, 2.6× fragments). Prefer workbench resolution rates and per-statement closure deltas for reviewability judgment.

### 2.2 Review Workbench resolution (same logic as Statement Review Workbench)

| Outcome | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Exact internal resolution | 106 | 258 | 152 |
| Partial resolution (parent fallback) | 52 | 0 | -52 |
| Container-only resolution | 28 | 315 | 287 |
| Unresolved | 11 | 45 | 34 |
| External reference | 27 | 37 | 10 |

### 2.3 Structural fragmentation capability

| Fragment type | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `regulation:*:paragraph:*` | 0 | 448 | 448 |
| `article:*:paragraph:*` | 0 | 0 | 0 |
| `rule:*:paragraph:*` | 0 | 0 | 0 |

## 3. Reviewability

**Statements previously blocked by unresolved context, now reviewable:** 0 (matched on normalised statement text).

**Statements with workbench-unresolved context now fully resolved:** 0.

A statement is treated as *blocked* when it carries the `unresolved_context` quality flag, has `standalone_status: partially_resolved`, or has at least one workbench-unresolved required-context locator.

**Statements affected by regulation/article paragraph fragmentation references:** 17 matched statements cite regulation/article paragraph locators in `required_context`.
**Matched statements with improved context closure (Δ > 0):** 15 of 157 text-matched pairs.

## 4. Evidence quality

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Source fragments with corruption signals | 146 | 118 | -28 |
| Propositions with corrupt evidence quotes | 161 | 144 | -17 |
| Matched propositions (by source + text) with changed evidence quotes | — | — | 55 / 213 matched |
| Matched propositions where corrupt evidence became clean | — | — | 14 |

Corruption detection uses Review Workbench `detectExcerptCorruption()` heuristics plus legacy token scan (`181The`, `amake`, `andbassess`, `361Before`, `m anure`).

## 5. Top 20 statements — largest context-closure improvement

Closure score: `1.0` per exact workbench resolution, `0.5` per partial, divided by required-context count (statements with no required context score `1.0`).

| Δ closure | Before → After exact | Statement |
| ---: | --- | --- |
| +0.50 | 0 → 2 | A report under regulation 40A(1) must contain the map published under regulation 3(2), accompanied by a statement detailing the nature of, a… |
| +0.50 | 0 → 1 | A person who contravenes regulation 3(1) or (4), 4(1), 5(1) or 7(4A) is guilty of an offence and liable on summary conviction to a fine not … |
| +0.50 | 0 → 1 | An expression used in regulation 13(1) and in the Environmental Civil Sanctions (England) Order 2010 has the same meaning in regulation 13(1… |
| +0.50 | 0 → 1 | A person who contravenes regulation 3(1) or (4), 4(1), 5(1) or 7(4A) is guilty of an offence and liable on conviction on indictment to a fin… |
| +0.50 | 0 → 1 | If proposals for an alternative suite of measures for delivering the outcomes in regulation 44(1) are received within 18 months of these Reg… |
| +0.50 | 0 → 1 | A report under regulation 40A(1) must contain details of any steps taken to promote good agricultural practice. |
| +0.50 | 0 → 1 | An expression used in regulation 42(1) and in the Environmental Civil Sanctions (England) Order 2010 has the same meaning in regulation 42(1… |
| +0.50 | 0 → 1 | In the exercise of its functions, the Agency must have regard to any guidance issued by the Secretary of State under regulation 15(1). |
| +0.50 | 0 → 1 | In regulation 26, 'storage period' has the meaning given in regulation 25(7). |
| +0.50 | 0 → 1 | The occupier of a holding must maintain a record of the total size of the holding calculated in accordance with regulation 4(3). |
| +0.50 | 0 → 1 | An owner or occupier of a relevant holding who is sent a notice under regulation 5(3)(b) or 5(3A)(b) may appeal to the First-tier Tribunal a… |
| +0.50 | 0 → 1 | The Secretary of State must publish any guidance issued under regulation 15(1) on a website maintained by or on behalf of the Secretary of S… |
| +0.25 | 1 → 2 | Where the amount of storage capacity of a holding changes, the occupier must update the record required by regulation 36(1)(b) of the old Re… |
| +0.25 | 1 → 2 | Regulation 24 (separation of slurry) does not apply in relation to a new holding until 31st July in the third calendar year after the year i… |
| +0.13 | 0 → 1 | The occupier of a new holding must record the total size of the holding, calculated in accordance with regulation 7(4). |

## 6. Verdict

Structural-fidelity improvements **measurably improved reviewability** on the slurry corpus, with caveats:

1. **Context anchoring improved:** exact workbench resolutions more than doubled (106 → 258), while partial parent-fallback resolutions dropped to zero (52 → 0). Regulation paragraph children (448 locators) enable paragraph-level excerpts instead of monolithic parent regulations.
2. **Evidence is cleaner but not clean:** corrupt fragments fell 28 (146 → 118); corrupt evidence quotes fell 17. Residual corruption remains in 118 fragments.
3. **Scale confounds headline counts:** export-unresolved references and `partially_resolved` statements grow with re-extraction volume (730 → 1415 statements). 15 matched statements show strictly improved context closure; 0 matched statements moved from blocked to reviewable.
4. **Not legal validation:** this measures whether a reviewer can locate faithful source excerpts and resolve internal cross-references — not whether propositions are legally correct.

## Methodology

- Comparison uses exported bundles under `law-proposition-extractor/runs/`.
- **Before:** stale 279-fragment intake (`slurry-gb-principal-5-current-export-json-repaired`). Effective-law statements derived deterministically from exported propositions when absent from bundle root.
- **After:** frontier re-export on 727-fragment intake (`slurry-gb-principal-5-current-export`).
- Statement pairing for deltas uses normalised `statement_text` (case/whitespace folded).
- Workbench resolution reuses `buildContextRequirementResolutions()` from the Review Workbench.

