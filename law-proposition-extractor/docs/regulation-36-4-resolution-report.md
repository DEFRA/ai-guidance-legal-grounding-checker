# Regulation 36(4) partial resolution — diagnostic report

**Prompt:** 75-BR1  
**Run inspected:** `law-proposition-extractor/runs/slurry-gb-principal-5-current-export-json-repaired`  
**Date:** 2026-06-11  
**Conclusion:** `regulation 36(4)` was **partially resolved** because source fragments stopped at `regulation:36` (whole-regulation granularity). CLML provides paragraph-level child nodes (`regulation-36-4`, etc.) but the legislation structural splitter did not emit them.

**Update (Prompt 76-BR1A):** Phase 1 implemented — `_build_legislation_structural_fragments` now emits `regulation|article|rule:{n}:paragraph:{p}` child fragments from CLML P2 nodes while retaining parent provision fragments. Locator resolution prefers exact colon-path paragraph matches before parent fallback. Re-ingestion required for existing exports to pick up new fragments.

**Update (Prompt 79-BR1, 2026-06-11):** P1 provision-numbering serialisation fixed in `clml_text.py` — live WSI CLML uses `<Pnumber>36</Pnumber>` (no trailing dot, often with `CommentaryRef` siblings). Numbers were incorrectly rendered as `(36)` instead of `36.` when followed by `P1para` wrappers. Pre-flight intake verification now passes: `regulation:36` → `36. (1) Before…`, `regulation:36:paragraph:4` → `(4) The occupier must make a record…`, zero corrupt excerpt tokens. Caches cleared; **frontier re-export blocked** (`ANTHROPIC_API_KEY` unset). See `runs/slurry-gb-principal-5-current-export/REGENERATION_79_BR1.md`.

---

## Summary

| Question | Answer |
|----------|--------|
| Is partial resolution caused by coarse fragments? | **Yes** |
| Are `regulation:36:paragraph:*` child fragments present? | **No** (0 in export) |
| Is paragraph (4) text inside parent `regulation:36`? | **Yes** (both instruments) |
| Does CLML XML expose subparagraph nodes? | **Yes** (`regulation-36-4` P2 nodes; deeper P3/P4 under some paragraphs) |
| Root cause in pipeline | `_build_legislation_structural_fragments` only matches root provision IDs (`regulation-36`); schedule paragraphs are split, regulation paragraphs are not |

Context locator resolution (`context-locator-resolution.ts`) already supports exact match on `regulation:36:paragraph:4` and falls back to `partially_resolved` on parent `regulation:36` when the child fragment is missing (see unit tests).

---

## Triggering cross-reference (Wales)

Proposition `prop:354740990a81acd6` (Schedule 1A, paragraph 18(1)(b)) states:

> The occupier must assess and record the amount of nitrogen (kg) … in accordance with **regulation 36(4)** and Parts 1 and 2 of Schedule 3.

| Field | Value |
|-------|-------|
| `source_record_id` | `lex-805b03f284dcf364` |
| Host fragment | `frag-lex-805b03f284dcf364-071` (`schedule:1a:paragraph:18`) |
| `explicit_cross_reference_targets` | `regulation 36`, `schedule 3` (paragraph sub-citation not normalised to `regulation 36(4)`) |

When `regulation 36(4)` is resolved against Wales fragments, only `regulation:36` matches → **`partially_resolved`**, `unresolvedChild: paragraph (4)`.

---

## Source fragment inventory — `regulation:36*`

### Wales — WSI 2021/77 (`lex-805b03f284dcf364`)

| Field | Value |
|-------|-------|
| `source_record_id` | `lex-805b03f284dcf364` |
| `source_snapshot_id` | `snap-lex-805b03f284dcf364-v1` |
| `source_url` | `https://www.legislation.gov.uk/wsi/2021/77/data.xml` |
| Fragment `id` | `frag-lex-805b03f284dcf364-038` |
| `locator` | `regulation:36` |
| `parent_fragment_id` | `frag-lex-805b03f284dcf364-001` |
| `fragment_text` length | **1,844** chars |
| `fragmentation_strategy` | `legislation_structural` |

**Locators matching `regulation:36*`:** `regulation:36` only.

**Child locators:**

| Locator | Present |
|---------|---------|
| `regulation:36:paragraph:1` | No |
| `regulation:36:paragraph:2` | No |
| `regulation:36:paragraph:3` | No |
| `regulation:36:paragraph:4` | No |

**Paragraph (4) in parent text:** Yes — substring at offset ~704:

> `4The occupier must make a record of the calculations and how the final figures were arrived at.`

**Corpus asymmetry (same instrument):** 51 regulation-root fragments, **0** regulation-paragraph fragments, **47** schedule-paragraph fragments (`schedule:*:paragraph:*`).

---

### England — UKSI 2015/668 (`lex-120b4f9c395b3f94`)

| Field | Value |
|-------|-------|
| `source_record_id` | `lex-120b4f9c395b3f94` |
| `source_snapshot_id` | `snap-lex-120b4f9c395b3f94-v1` |
| `source_url` | `https://www.legislation.gov.uk/uksi/2015/668/data.xml` |
| Fragment `id` | `frag-lex-120b4f9c395b3f94-039` |
| `locator` | `regulation:36` |
| `parent_fragment_id` | `frag-lex-120b4f9c395b3f94-001` |
| `fragment_text` length | **1,982** chars |
| `fragmentation_strategy` | `legislation_structural` |

**Locators matching `regulation:36*`:** `regulation:36` only.

**Child locators:** none (`regulation:36:paragraph:1` … `4` all absent).

**Paragraph (4) in parent text:** Yes — substring at offset ~680:

> `4A derogation granted under this regulation ceases to have effect unless the occupier … written declaration that the conditions set out in Schedule 3 … will be met`

(England reg 36(4) is a derogation-declaration obligation — different substance from Wales reg 36(4).)

**Corpus asymmetry:** 48 regulation-root fragments, **0** regulation-paragraph fragments, **23** schedule-paragraph fragments.

---

## CLML / XML structural evidence

Fetched live from `legislation.gov.uk` `data.xml` payloads (2026-06-11).

### Wales `regulation-36` subtree

| CLML `id` | Tag | Text length | Would map to |
|-----------|-----|-------------|--------------|
| `regulation-36` | P1 | 1,855 | `regulation:36` (parent — current) |
| `regulation-36-1` | P2 | 271 | `regulation:36:paragraph:1` |
| `regulation-36-2` | P2 | 157 | `regulation:36:paragraph:2` |
| `regulation-36-3` | P2 | 274 | `regulation:36:paragraph:3` |
| `regulation-36-4` | P2 | **95** | `regulation:36:paragraph:4` |
| `regulation-36-5` | P2 | 98 | `regulation:36:paragraph:5` |
| `regulation-36-6` | P2 | 947 | `regulation:36:paragraph:6` |
| `regulation-36-1-a`, `regulation-36-1-b` | P3 | 142, 58 | subparagraph nodes under para 1 |
| `regulation-36-3-a`, `regulation-36-3-b` | P3 | 45, 141 | subparagraph nodes under para 3 |

### England `regulation-36` subtree (excerpt)

| CLML `id` | Tag | Text length | Would map to |
|-----------|-----|-------------|--------------|
| `regulation-36` | P1 | 1,982 | `regulation:36` |
| `regulation-36-4` | P2 | 276 | `regulation:36:paragraph:4` |
| `regulation-36-4A` | P2 | 109 | `regulation:36:paragraph:4a` |
| `regulation-36-7-a`, `regulation-36-7-a-i` | P3/P4 | 262, 173 | nested subparagraph nodes |

**Observation:** Paragraph-level P2 nodes are first-class CLML elements with stable `id` attributes. The adapter already iterates all nodes but only assigns locators for:

- `_RE_ROOT_PROVISION_ID` → `regulation:36`
- `_RE_SCHEDULE_PARAGRAPH_ID` / `_RE_SCHEDULE_NUMERIC_PARAGRAPH_ID` → `schedule:N:paragraph:P`

Regulation/article/rule paragraph IDs (`regulation-36-4`) fall through unmatched.

`metadata.structural_fragments` on both source records likewise contains a single `regulation:36` row per instrument (no paragraph children).

---

## Resolution behaviour (existing, unchanged)

From `law-proposition-extractor/apps/web/lib/context-locator-resolution.ts`:

1. Try exact match on `regulation:36:paragraph:4` → none in export.
2. Fall back to parent `regulation:36` → single match → `exportResolutionStatus: "partially_resolved"`, `resolutionMode: "partial"`, `unresolvedChild: "paragraph (4)"`.

Covered by tests in `context-locator-resolution.test.ts` (`partially resolves regulation 36(4) to regulation 36 when only parent fragment exists`).

---

## Fix implemented (Prompt 76-BR1A)

**Phase 1 — P2 paragraphs** in `law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/sources/adapters.py`:

- `_RE_PROVISION_PARAGRAPH_ID` matches `regulation-36-4`, `article-12-2`, `rule-5-3`, etc.
- Child locator `{unit_kind}:{unit_number}:paragraph:{para_number}`; parent locator retained on container rows.
- Child `fragment_text` from `serialize_clml_text()` on the P2 node only (not the whole regulation).
- Regression tests: `law-proposition-extractor/tests/unit/test_legislation_gov_uk_adapter.py`, `law-proposition-extractor/apps/web/lib/context-locator-resolution.test.ts`.

**Keep parent container:** `regulation:36` still emitted from `regulation-36` P1 — whole-regulation extraction and existing proposition anchors unchanged at locator level.

### Phase 2 (optional, later) — P3+ subparagraphs

CLML uses IDs like `regulation-36-1-a`, `regulation-36-7-a-i`. Only needed if locators like `regulation 36(7)(a)(i)` must resolve exactly. Not required for the 75-BR1 case.

### Fragment ID migration impact

Current IDs are order-assigned during `expand_monolithic_source_fragment` (`frag-{slug_base}-{order:03d}`).

| Impact | Detail |
|--------|--------|
| Existing `regulation:36` fragment IDs | **Stable** if parent row kept and new paragraph rows appended after it in `structural_fragments` order |
| Downstream fragment order indices | Paragraph children inserted between parent regulation and next regulation will **shift** suffix numbers for all subsequent fragments in that source (e.g. current `frag-lex-805b03f284dcf364-039` may become `-045` after ~6 new children) |
| Propositions keyed to `source_fragment_id` | Re-extract or repair pass required for propositions bound to shifted fragment IDs |
| Locator-based joins | Prefer `locator` + `source_record_id` over raw `fragment_id` where possible — locators for existing roots unchanged |
| New paragraph fragments | New IDs; no migration from old IDs (paragraph fragments did not exist) |

**Recommendation:** treat as a **re-ingestion / re-fragmentation** change with a one-time repair mapping `{source_record_id, locator} → fragment_id`, not an in-place ID preservation for inserted rows.

**Decision for 76-BR1A:** fragment IDs remain **ordinal** (`frag-{source_slug}-{order:03d}`) for this change. No locator-derived stable ID migration in this prompt — no existing safe helper was wired through intake + expansion. Locator-derived IDs (`frag-{source_slug}-{locator-slug}`) should be considered in a follow-up if fragment ID churn blocks review workbench round-trips.

| Downstream surface | Expected impact after re-ingestion |
|--------------------|-----------------------------------|
| Extraction derived cache | **Clear** — chunk boundaries and fragment IDs change for sources with new paragraph rows |
| Source snapshot cache | **Clear** — `metadata.structural_fragments` is rebuilt at fetch/parse |
| Propositions (`source_fragment_id`) | **Re-extract or repair** — IDs after the first inserted paragraph child shift |
| Locator-based joins | **Stable** — `regulation:36` locator unchanged; new `regulation:36:paragraph:*` locators appear |
| Review workbench exports | **Load-compatible** — old exports open but `source_fragment_id` pointers may be stale until re-export |

---

## Regeneration (slurry corpus)

**Status (2026-06-11):** Pre-flight complete; frontier export pending credentials. Full log: `runs/slurry-gb-principal-5-current-export/REGENERATION_79_BR1.md`.

From `law-proposition-extractor/`:

```bash
# 0. Pre-flight (no LLM) — must pass before frontier export
uv run --package law-proposition-extractor-pipeline python scripts/verify_regulation_paragraph_fragmentation.py \
  --case runs/slurry-gb-principal-5-current/case.json \
  --source-cache-dir runs/slurry-gb-principal-5-current/.source-cache

# 1. Drop cached legislation.gov.uk snapshots (parsed structural_fragments are cached)
rm -f runs/slurry-gb-principal-5-current/.source-cache/*.json
rm -rf "${TMPDIR:-/tmp}/law-proposition-extractor/source-snapshots"/*

# 2. Drop derived extraction cache for the target run
rm -rf runs/slurry-gb-principal-5-current/.derived-cache

# 3. Re-run intake + extraction + export (frontier mode)
just litellm   # requires ANTHROPIC_API_KEY
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline run-and-export-case \
  runs/slurry-gb-principal-5-current/case.json \
  --output-dir runs/slurry-gb-principal-5-current-export \
  --source-cache-dir runs/slurry-gb-principal-5-current/.source-cache \
  --derived-cache-dir runs/slurry-gb-principal-5-current/.derived-cache \
  --use-llm \
  --extraction-mode frontier
```

Requires LiteLLM (`just litellm`) and `ANTHROPIC_API_KEY` for `--extraction-mode frontier`. **Do not** fall back to local mode for this regeneration. **Do not** assume old review annotations keyed by `frag-lex-*-NNN` survive without repair.

---

## Acceptance check (post-fix)

After implementing Phase 1 and re-running intake/fragmentation for the slurry corpus:

1. Wales export contains `regulation:36:paragraph:4` on `lex-805b03f284dcf364` with ~95-char body matching CLML `regulation-36-4`.
2. `resolveContextRequirement({ locator: "regulation 36(4)" }, …)` returns `resolutionMode: "exact"`, `exportResolutionStatus` ≠ `partially_resolved`.
3. Parent `regulation:36` fragment still present for whole-regulation extraction jobs.
4. Schedule paragraph fragmentation unchanged.

Cheap verification (no LLM): `law-proposition-extractor/docs/dev/regulation-paragraph-fragmentation-verification.md`

---

## References

- Export artifacts: `law-proposition-extractor/runs/slurry-gb-principal-5-current-export-json-repaired/source_fragments.json`
- Structural builder: `law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/sources/adapters.py` (`_build_legislation_structural_fragments`)
- Fragment expansion: `law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/source_fragmentation.py` (`legislation_structural`)
- Locator resolution: `law-proposition-extractor/apps/web/lib/context-locator-resolution.ts`
- Unit tests: `law-proposition-extractor/apps/web/lib/context-locator-resolution.test.ts` (regulation 36(4) cases)
