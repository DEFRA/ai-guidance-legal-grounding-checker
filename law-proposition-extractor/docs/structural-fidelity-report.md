# Structural-fidelity benchmark report

**Date:** 2026-06-11  
**Scope:** Prompt 79-BR1 and preceding CLML intake fixes (Prompts 76–78-BR1)  
**Corpus:** Slurry GB principal-5 (`runs/slurry-gb-principal-5-current`)  
**Status:** Pre-flight source intake **passed**; frontier re-export **pending** (`ANTHROPIC_API_KEY` unset)

This report captures how structural-fidelity work improved legal source representation **before** downstream proposition extraction and export regeneration. It is retrospective documentation, not executable logic.

---

## Executive summary

Stale exports (2026-06-04) embedded three classes of structural defect at legislation.gov.uk intake:

1. **`itertext()` corruption** — numbering and list-label siblings glued into prose (`181The`, `amake`, `andbassess`).
2. **`P*para` wrapper omission** — live CLML nests operative text under `P1para`…`P4para`; treating wrappers as inline markup collapsed provisions to number labels only (`(36)`, `(4)`).
3. **Numbering-style mismatch (79-BR1)** — P1 `Pnumber` nodes without a trailing dot (`36` not `36.`) were serialised as sub-paragraph markers `(36)` instead of provision markers `36.`.

Together these defects produced **279 coarse fragments**, **zero** regulation/article/rule paragraph children, and forced **partial locator resolution** (e.g. `regulation 36(4)` → parent `regulation:36` only).

After cache clears and the full fix stack, fresh intake for the same case yields **727 fragments**, **448** `regulation:*:paragraph:*` children, **zero** corruption tokens, and **exact** resolution capability for `regulation 36(4)` → `regulation:36:paragraph:4`.

---

## 1. Defects discovered

### 1.1 `itertext()` corruption

**Mechanism:** `adapters.py` used `"".join(node.itertext())`, flattening CLML sibling elements (`Pnumber`, list labels) into contiguous prose.

**Symptom patterns:**

| Pattern | Example (corrupt) | Expected |
| --- | --- | --- |
| Locator label bleed | `181The occupier must—` | `18.(1) The occupier must—` |
| Glued list marker | `amake a record` | `(a) make a record` |
| Glued continuation | `andbassess and record` | `and (b) assess and record` |
| Provision number bleed | `361Before the relevant date` | `36. (1) Before the relevant date` |
| Mid-word split | `m anure` | `manure` |

**Fix:** Structure-aware `serialize_clml_text()` in `clml_text.py` (Prompt 77-BR1 era). Regression: `test_clml_text.py`, `test_legislation_gov_uk_adapter.py`.

**Earliest corrupt stage:** `source_fragment_extraction` — corruption is present in `source_fragments.json` before any web workbench or proposition layer touches the text. See `excerpt-corruption-report.md`.

### 1.2 `P*para` wrapper omission

**Mechanism:** Live legislation.gov.uk CLML nests operative prose under `P1para` / `P2para` / `P3para` / `P4para` inside provision containers. `serialize_clml_text()` treated these as inline markup; `_inline_text()` skips block children, so each node serialised to its number label only.

**Symptom:** `regulation-36` → body `(36)` (3 chars, filtered as noise); `regulation-36-4` → `(4)`. No `regulation:36:paragraph:*` locators emitted despite P2 child nodes existing in XML.

**CLML shape (WSI 2021/77 regulation 36):**

| Element | Tag | `id` | Notes |
| --- | --- | --- | --- |
| Provision container | `P1` | `regulation-36` | Children: `Pnumber`, `P1para` |
| Paragraph wrapper | `P1para` | *(none)* | Contains `P2` × 6 (`regulation-36-1` … `regulation-36-6`) |
| Paragraph provision | `P2` | `regulation-36-4` | Prose under `P2para` → `Text` |

**Fix (Prompt 78-BR1):** Treat `P1para`…`P4para` as block containers; apply pending `Pnumber` labels before recursing. Fixture: `wsi_2021_77_regulation_36_live_clml.xml`.

### 1.3 Missing provision paragraph fragments

**Mechanism:** Even after P2 paragraph emission (Prompt 76-BR1A in `adapters.py`), the `P*para` serialisation bug prevented paragraph bodies from surviving intake. The adapter iterated CLML nodes with stable `id` attributes (`regulation-36-4`, etc.) but structural text was empty or noise.

**Corpus asymmetry (stale export):** 51 regulation-root fragments and **0** regulation-paragraph fragments on Wales WSI 2021/77, versus **47** schedule-paragraph fragments — schedule splitting worked; regulation paragraph splitting did not surface usable rows.

### 1.4 Numbering-style mismatch (Prompt 79-BR1)

**Mechanism:** `_append_number_for_child()` inferred numbering style from the **following** child tag. When a P1 `Pnumber` (`36`, no trailing dot, often with `CommentaryRef` siblings) was followed by `P1para` rather than `Text`, the serializer treated it as a sub-paragraph label → `(36)` instead of a provision marker → `36.`.

**Numbering style table (post-fix):**

| Parent CLML level | Style | Example |
| --- | --- | --- |
| P1 | provision | `36. Before the relevant date…` |
| P2 | paragraph | `(1) Paragraph text…` |
| P3 | list | `(a) Item text…` |
| P4+ | nested | `(i) Nested item…` |

**Fix:** `_append_number_for_child()` now selects style from CLML parent level, not child tag alone.

---

## 2. Metrics before / after

Benchmark corpus: slurry principal-5 case sources. **Before** = stale export (`runs/slurry-gb-principal-5-current-export`, 2026-06-04). **After (intake)** = fresh re-ingestion verified 2026-06-11 (pre-flight, no LLM). **After (export)** = frontier re-export not yet completed.

| Metric | Before (stale export) | After (fresh intake) | After (frontier export) |
| --- | ---: | ---: | ---: |
| Source fragment count | 279 | 727 | *pending* |
| `regulation:*:paragraph:*` children | 0 | 448 | *pending* |
| `article:*:paragraph:*` children | 0 | 0 | *pending* |
| `rule:*:paragraph:*` children | 0 | 0 | *pending* |
| Schedule locators (WSI 2021/77 intake) | present | 141 | *pending* |
| Corrupt excerpt hits | see below | 0 | *pending* |

### Corruption token scan (stale export)

Automated scan of `source_fragments.json` fragment text across the stale export:

| Token | Occurrences |
| --- | ---: |
| `181The` | 2 |
| `amake` | 4 |
| `andbassess` | 2 |
| `361Before` | 1 |
| `m anure` | 0 |

Fresh intake (2026-06-11): **zero** hits for all patterns above.

### Locator resolution capability

| Locator query | Before | After (intake + resolution layer) |
| --- | --- | --- |
| `regulation 36` | exact → `regulation:36` | exact → `regulation:36` |
| `regulation 36(4)` | **partial** → parent `regulation:36`; `unresolvedChild: paragraph (4)` | **exact** → `regulation:36:paragraph:4` |
| `schedule 1A paragraph 18` | exact (coarse schedule row) but corrupt body | exact with structurally faithful body |

Resolution behaviour is implemented in `context-locator-resolution.ts` and covered by 22 unit tests (`context-locator-resolution.test.ts`). The resolution layer was already correct; the bottleneck was missing/corrupt fragments at intake.

### Export-side `partially_resolved` baseline

Stale `effective_law_statements.json` (`slurry-gb-principal-5-one-shot-current-2-export`): **135 / 734** statements (18.4%) carry `standalone_status: "partially_resolved"`. At least one statement cites `regulation 36(4)` and inherits partial resolution from the missing paragraph fragment.

Post-regeneration resolution metrics require a completed frontier export with refreshed `source_fragments.json` and law-statement metadata.

---

## 3. Concrete examples

### 3.1 Regulation 36 parent — before / after

**Source:** Wales WSI 2021/77 (`lex-805b03f284dcf364`), locator `regulation:36`.

**Before** (stale export, `frag-lex-805b03f284dcf364-038`):

```
361Before the relevant date every year the occupier must make a record of—athe number and category … andbthe number of days … 2The occupier must then calculate … 4The occupier must make a record of the calculations …
```

- Provision number glued to paragraph 1 (`361Before`).
- List markers glued (`athe`, `andb`).
- Single monolithic fragment (1,844 chars); no paragraph children.

**After** (fresh intake, 2026-06-11):

```
36. (1) Before the relevant date every year the occupier must make a record of— (a) the number and category (in accordance with the categories in Schedule 1) of animals …
```

- Fragment id: `frag-lex-805b03f284dcf364-131`
- Text length: 958 chars (parent retains full regulation text with correct numbering)
- Six paragraph children emitted (`regulation:36:paragraph:1` … `:paragraph:6`)

### 3.2 Regulation 36(4) — before / after

**Before:**

| Field | Value |
| --- | --- |
| Locator children | none (`regulation:36:paragraph:4` absent) |
| Paragraph (4) text | embedded in parent at ~offset 704: `4The occupier must make a record of the calculations…` (number glued) |
| Resolution | `partially_resolved`, `resolutionMode: "partial"`, `unresolvedChild: "paragraph (4)"` |

**After:**

| Field | Value |
| --- | --- |
| Locator | `regulation:36:paragraph:4` |
| Fragment id | `frag-lex-805b03f284dcf364-135` |
| Parent | `frag-lex-805b03f284dcf364-131` |
| Text (98 chars) | `(4) The occupier must make a record of the calculations and how the final figures were arrived at.` |
| Resolution | `resolutionMode: "exact"`; `exportResolutionStatus` ≠ `partially_resolved` |

**Triggering cross-reference:** Proposition on `schedule:1a:paragraph:18` cites compliance with `regulation 36(4)` and Parts 1 and 2 of Schedule 3. Before the fix, Wales fragment inventory matched only `regulation:36`.

### 3.3 Schedule 1A paragraph 18 — before / after

Canonical corruption exemplar (`frag-lex-805b03f284dcf364-071`, locator `schedule:1a:paragraph:18`).

**Before:**

```
181The occupier must—amake a record of the type and amount of livestock manure … andbassess and record the amount of nitrogen (kg) … in accordance with regulation 36(4) and Parts 1 and 2 of Schedule 3.
```

Proposition `evidence_quote` copied the corrupt fragment span verbatim; display-layer regex partially masked `181The` → `181 The` and `amake` → `a make` but left `andbassess` and false `181` labels.

**After** (regression fixture output from structure-aware serialisation):

```
18(1) The occupier must— (a) make a record of livestock manure, and (b) assess and record the amount of nitrogen.
```

Live intake applies the same serialisation path. Assertions: `181The`, `amake`, `andbassess` must not appear (`test_legislation_gov_uk_adapter.py`).

---

## 4. Downstream implications

### 4.1 Review Workbench context closure

Context locator resolution reads `source_fragments` rows and matches colon-path locators before parent fallback. With paragraph children present:

- `regulation 36(4)` resolves **exactly** to a ~98-char excerpt instead of a ~958-char parent regulation.
- Assessment context panels show the operative paragraph, not a whole-regulation dump with glued numbers.
- `unresolvedChild` warnings for regulation paragraph citations should drop for re-ingested sources.

Surgical `source_fragments.json` swap validates resolution **without** full export regeneration (see `regulation-paragraph-fragmentation-verification.md`).

### 4.2 Proposition evidence quality

Frontier extraction requires `evidence_text` copied verbatim from source chunks. Corrupt fragment text propagated to:

- `propositions[].extraction_debug_meta.evidence_quote`
- `effective_law_statements[].statement_recipe[].source_excerpt`

After regeneration, evidence spans will contain correctly spaced numbering and list markers, improving auditability and reducing false-positive corruption flags from `detectExcerptCorruption()`.

### 4.3 Effective-law provenance

Effective-law statements bind context requirements to resolved fragments. Partial resolution stamped `standalone_status: "partially_resolved"` on statements whose cross-references could not anchor to a precise fragment. Exact paragraph fragments enable:

- Tighter `source_excerpt` boundaries in statement recipes
- Clearer provenance chains in `excerpt-provenance.ts` stage traces (stage 1 no longer the sole corrupt origin)

### 4.4 Expected reduction in `partially_resolved` references

Not all 135 stale `partially_resolved` statements will flip — many reflect genuinely coarse locators, cross-instrument references, or container-only citations. Expected improvements:

| Category | Expected change |
| --- | --- |
| `regulation N(M)` / `article N(M)` with P2 children now emitted | partial → **exact** |
| Corrupt parent text driving false partial signals | partial → **exact** (same locator, faithful excerpt) |
| `regulation 36(7)(a)(i)`-style P3/P4 nesting | remains partial until Phase 2 fragmentation |
| External / cross-instrument references | unchanged (`external_reference`) |

Conservative estimate: regulation-paragraph child emission across **448** new locators addresses the dominant structural gap; frontier re-export will quantify the net `partially_resolved` delta.

---

## 5. Open issues

### 5.1 P3/P4 list-item fragmentation

CLML exposes subparagraph nodes (`regulation-36-1-a`, `regulation-36-7-a-i`) as P3/P4 elements. Phase 1 (Prompt 76-BR1A) emits P2 paragraph children only. Locators like `regulation 36(7)(a)(i)` cannot resolve exactly until P3+ fragmentation is implemented.

List-item **text** within a schedule or regulation paragraph is now serialised correctly (`(a)`, `(b)` boundaries preserved), but **separate fragment rows** for nested list items are not yet emitted.

### 5.2 Stable locator-derived fragment ids

Fragment ids remain **ordinal** (`frag-{source_slug}-{order:03d}`). Inserting paragraph children shifts suffix indices for all subsequent fragments in a source. Locator-based joins (`regulation:36:paragraph:4`) are stable; `source_fragment_id` pointers on propositions and review annotations are not.

Follow-up: locator-derived ids (e.g. `frag-{slug}-regulation-36-paragraph-4`) to survive re-ingestion without repair passes. Explicitly out of scope for 79-BR1.

### 5.3 External cross-instrument context closure

`context-locator-resolution.ts` returns `external_reference` for locators outside the current source record (e.g. EU directive annex references, cross-WSI citations). Structural fidelity fixes apply per-source at intake; they do not close context across instrument boundaries.

Schedule 1A paragraph 18 cites `regulation 36(4)` **within** WSI 2021/77 — now exactly resolvable. Citations to England UKSI 2015/668 regulation 36(4) (different substance: derogation declaration) require the corresponding source record in the active fragment set.

---

## Verification evidence

| Artifact | Path |
| --- | --- |
| Pre-flight regeneration log | `runs/slurry-gb-principal-5-current-export/REGENERATION_79_BR1.md` |
| Regulation 36 verification (PASS) | `runs/slurry-gb-principal-5-current-export/REGULATION_PARAGRAPH_FRAGMENTATION_VERIFICATION.md` |
| Verification JSON | `runs/slurry-gb-principal-5-current-export/regulation_paragraph_fragmentation_verification.json` |
| Excerpt corruption investigation | `docs/excerpt-corruption-report.md` |
| Regulation 36(4) diagnostic | `docs/regulation-36-4-resolution-report.md` |
| Fragmentation verification guide | `docs/dev/regulation-paragraph-fragmentation-verification.md` |

### Commands re-run to reproduce intake benchmark

```bash
cd law-proposition-extractor
uv run --package law-proposition-extractor-pipeline python scripts/verify_regulation_paragraph_fragmentation.py \
  --case runs/slurry-gb-principal-5-current/case.json \
  --source-cache-dir runs/slurry-gb-principal-5-current/.source-cache \
  --output-dir runs/slurry-gb-principal-5-current-export

cd apps/web && npm test -- context-locator-resolution.test.ts
```

Frontier re-export (when `ANTHROPIC_API_KEY` available): see `REGENERATION_79_BR1.md` § Frontier re-export.

---

## Code touchpoints

| Component | Role |
| --- | --- |
| `packages/pipeline/src/law_proposition_extractor_pipeline/sources/clml_text.py` | Structure-aware CLML serialisation; numbering-style fix (79-BR1) |
| `packages/pipeline/src/law_proposition_extractor_pipeline/sources/adapters.py` | `_build_legislation_structural_fragments` — P2 paragraph emission |
| `apps/web/lib/context-locator-resolution.ts` | Exact vs partial locator resolution |
| `apps/web/lib/excerpt-provenance.ts` | Corruption stage tracing (diagnostic) |

---

## Related prompts (timeline)

| Prompt | Change |
| --- | --- |
| 76-BR1A | Emit `regulation\|article\|rule:{n}:paragraph:{p}` from CLML P2 nodes |
| 77-BR1 | Replace `itertext()` with `serialize_clml_text()` |
| 78-BR1 | Treat `P*para` wrappers as block containers |
| **79-BR1** | Fix P1 provision numbering style when `Pnumber` lacks trailing dot |

Prompt 79-BR1 is the capstone that made live WSI 2021/77 intake pass deterministic pre-flight verification; downstream regeneration remains blocked on frontier credentials.
