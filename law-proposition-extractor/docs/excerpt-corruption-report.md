# Excerpt corruption investigation report

**Date:** 2026-06-11  
**Scope:** Review Workbench source/legal excerpts beyond display-layer whitespace repair.

## Summary

Corruption in the examples below originates at **source fragment extraction** during legislation.gov.uk XML intake. It is already present in exported `source_fragments.json`, `source_snapshots.json`, and `sources.json` before the web workbench reads them. The workbench only partially masks it via `normalizeExcerptDisplay`; it does not introduce new corruption.

**Law Proposition Extractor exports require regeneration** after fixing the pipeline parser. Workbench display regexes are not an acceptable root-cause fix.

## Examples investigated

| Symptom | Raw export example | Earliest corrupt stage |
| --- | --- | --- |
| Locator label bleed (`181The` → should be `18.(1) The`) | `frag-lex-805b03f284dcf364-071` / `schedule:1a:paragraph:18` | `source_fragment_extraction` |
| Glued list marker (`amake` → `(a) make`) | same fragment + `evidence_quote` on `prop:bcf538e48efe0715` | `source_fragment_extraction` (propagates to `evidence_quote`) |
| Glued continuation (`andbassess` → `and (b) assess`) | same fragment | `source_fragment_extraction` |
| Internal word space (`m anure` → `manure`) | same `itertext()` class; not in this fragment’s export but detected by debugger | `source_fragment_extraction` |

Canonical export fragment opening (verbatim):

```
181The occupier must—amake a record … andbassess and record …
```

Proposition text is clean (LLM normalised); `evidence_quote` copies the corrupt fragment span:

```
The occupier must—amake a record of the type and amount of livestock manure …
```

## Pipeline stage comparison

Provenance debugger: `law-proposition-extractor/apps/web/lib/excerpt-provenance.ts`  
Fixture: `law-proposition-extractor/apps/web/lib/excerpt-provenance-fixture.ts` (Schedule 1A paragraph 18 statement `lawstmt:76ca05f0819bcc2f`)

| Stage | Field | Corrupt? | Notes |
| --- | --- | --- | --- |
| 1. Source fragment extraction | `fragment_text` | **Yes** | Root cause |
| 2. Evidence quote generation | `extraction_debug_meta.evidence_quote` | **Yes** | Substring of corrupt fragment; hygiene backfill locates verbatim in corrupt haystack |
| 3. Statement recipe / export | `statement_recipe.source_excerpt` | **Yes** (when present) | Truncated corrupt prefix (`181The occupier must`) |
| 4. Excerpt assembly (workbench) | `assembled_excerpt` | **Yes** | Pass-through from fragment; no repair |
| 5. Display normalisation | `displaySourceExcerpt` | **Partially** | Fixes `181The`→`181 The`, `amake`→`a make`; leaves `andbassess`, `m anure`, false `181` label |

## Root cause (fixed 2026-06-11)

`law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/sources/adapters.py` previously used `"".join(node.itertext())` in `_build_legislation_structural_fragments` and `_extract_text_chunks`, which flattened CLML numbering/list-label siblings into prose (`181The`, `amake`, `andbassess`).

**Fix:** `law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/sources/clml_text.py` — structure-aware `serialize_clml_text()` walks CLML block/numbering siblings and preserves paragraph, sub-paragraph, and list-label boundaries. Regression tests: `law-proposition-extractor/tests/unit/test_clml_text.py`, `law-proposition-extractor/tests/unit/test_legislation_gov_uk_adapter.py`.

legislation.gov.uk CLML marks paragraph numbers (`Pnumber`), sub-paragraph numbers, and list item labels (`a`, `b`, …) as **sibling elements** to prose. Blind `itertext()` concatenation yielded `181The`, `amake`, `andbassess`, and mid-word splits such as `m anure`.

## Affected fields

- `source_snapshots[].authoritative_text`
- `sources[].authoritative_text`
- `source_fragments[].fragment_text`
- `metadata.structural_fragments[].text`
- `propositions[].extraction_debug_meta.evidence_quote` (derived from fragments)
- `effective_law_statements[].statement_recipe[].source_excerpt` (when exported)
- All workbench excerpt surfaces (law panel, proposition evidence, composition sources, assessment context)

## Regeneration required?

**Yes.** Existing run exports (e.g. `slurry-gb-principal-5-one-shot-current-2-export`) embed corrupt text at intake. After deploying the parser fix:

1. Clear cached legislation.gov.uk source snapshots (parsed payloads are cached).
2. Clear the run’s derived extraction cache (optional but recommended so evidence quotes are not reused).
3. Re-run source intake + proposition extraction + export for the slurry case.

From `law-proposition-extractor/`:

```bash
# 1. Drop cached legislation.gov.uk snapshots (default ops cache location)
rm -rf "${TMPDIR:-/tmp}/law-proposition-extractor/source-snapshots"/*

# 2. Drop slurry run derived extraction cache
rm -rf runs/slurry-gb-principal-5-one-shot-current-2/.derived-cache

# 3. Re-run and export (matches current slurry principal-5 frontier run)
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline run-and-export-case \
  runs/slurry-gb-principal-5-one-shot-current-2/case.json \
  --output-dir runs/slurry-gb-principal-5-one-shot-current-2-export \
  --derived-cache-dir runs/slurry-gb-principal-5-one-shot-current-2/.derived-cache \
  --use-llm \
  --extraction-mode frontier
```

Requires LiteLLM (`just litellm`) when using `--extraction-mode frontier`. Use explicit `--source-cache-dir` if the run used a non-default cache path.

Display-only workbench changes do not require export regeneration but also do not fix underlying data.

## Tooling added

- `buildWorkbenchExcerptProvenance()` — per-surface stage trace
- `tracePropositionExcerptProvenance()` — single-proposition debugger
- `detectExcerptCorruption()` — pattern flags (diagnostic only)
- `logWorkbenchExcerptProvenance()` — console grouping for manual inspection
- `summarizeExcerptCorruption()` — aggregate origin + affected fields

Run tests: `npm test -- lib/excerpt-provenance.test.ts` (from `law-proposition-extractor/apps/web`).
