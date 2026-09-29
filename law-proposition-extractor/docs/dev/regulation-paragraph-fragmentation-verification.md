# Regulation paragraph fragmentation verification

Cheap, deterministic checks for CLML regulation paragraph child fragments (Prompt 77-BR1). No LLM calls and no proposition extraction.

## Root cause (fixed 2026-06-11, Prompt 78-BR1)

**Symptom:** Offline fixture verification passed, but `--case runs/slurry-gb-principal-5-current/case.json` produced only `regulation:36` with body `(36)` and no `regulation:36:paragraph:1..4`.

**Cause:** Real legislation.gov.uk CLML nests operative prose under `P1para` / `P2para` / `P3para` / `P4para` wrappers inside provision containers. The simplified offline fixture placed `Text` and `P2` nodes as direct children of `P1`, so tests passed while live intake failed.

For WSI 2021/77 regulation 36 (live XML):

| Element | Tag | `id` | Children | Notes |
|---------|-----|------|----------|-------|
| Provision container | `P1` | `regulation-36` | `Pnumber`, `P1para` | Full regulation text lives under `P1para` |
| Number label | `Pnumber` | *(none)* | `CommentaryRef` | Sibling to `P1para`, not the provision id |
| Paragraph wrapper | `P1para` | *(none)* | `P2` × 6 | `regulation-36-1` … `regulation-36-6` are **descendants**, not siblings of `P1` |
| Paragraph provision | `P2` | `regulation-36-4` | `Pnumber`, `P2para` | Paragraph prose under `P2para` → `Text` |

`serialize_clml_text()` treated `P*para` wrappers as inline markup. `_inline_text()` skips block children (`P2`, `Text`, …), so each node serialised to its number label only — e.g. `regulation-36` → `(36)`, `regulation-36-4` → `(4)` (3 chars, filtered as noise). Paragraph locators were never emitted.

**Fix:** `law_proposition_extractor_pipeline/sources/clml_text.py` — treat `P1para`…`P4para` as block containers and apply pending `Pnumber` labels as if followed by `Text` before recursing into the wrapper. Regression fixture: `wsi_2021_77_regulation_36_live_clml.xml`.

## What it verifies

After refreshed source intake for WSI 2021/77 (slurry Wales principal), structural fragmentation must emit:

- `regulation:36`
- `regulation:36:paragraph:1`
- `regulation:36:paragraph:2`
- `regulation:36:paragraph:3`
- `regulation:36:paragraph:4`

Review Workbench context resolution already supports exact match on `regulation:36:paragraph:4` for the locator text `regulation 36(4)` — see `context-locator-resolution.test.ts` and the offline fixture `wsi-2021-77-regulation-36-fragments.ts`.

## Commands

### Offline fixture (default — no network)

```bash
cd law-proposition-extractor
uv run --package law-proposition-extractor-pipeline python scripts/verify_regulation_paragraph_fragmentation.py
```

Equivalent CLI entry point:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline verify-regulation-paragraph-fragments
```

### Re-ingest from slurry case (network fetch to legislation.gov.uk)

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline verify-regulation-paragraph-fragments \
  --case runs/slurry-gb-principal-5-current/case.json \
  --source-cache-dir runs/slurry-gb-principal-5-current/.source-cache
```

### Verify an existing export's `source_fragments.json` (no fetch)

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline verify-regulation-paragraph-fragments \
  --export-dir runs/slurry-gb-principal-5-current-export
```

Write markdown/JSON artifacts:

```bash
uv run --package law-proposition-extractor-pipeline python scripts/verify_regulation_paragraph_fragmentation.py \
  --output-dir /tmp/reg-36-verify
```

## Expected console output (fixture mode)

```
[PASS] regulation paragraph fragmentation (fixture)
authority_source_id=wsi/2021/77
source_record_id=lex-805b03f284dcf364
locator_prefix=regulation:36
matching locators:
  - regulation:36
  - regulation:36:paragraph:1
  - regulation:36:paragraph:2
  - regulation:36:paragraph:3
  - regulation:36:paragraph:4
fragment previews:
  regulation:36 (258 chars) parent=frag-lex-805b03f284dcf364-001
    36. Regulation 36 applies to nitrogen accounting. (1) Paragraph one of regulation 36. (2) Paragraph two of regulation 3…
  regulation:36:paragraph:1 (35 chars) parent=frag-lex-805b03f284dcf364-002
    (1) Paragraph one of regulation 36.
  regulation:36:paragraph:2 (35 chars) parent=frag-lex-805b03f284dcf364-002
    (2) Paragraph two of regulation 36.
  regulation:36:paragraph:3 (37 chars) parent=frag-lex-805b03f284dcf364-002
    (3) Paragraph three of regulation 36.
  regulation:36:paragraph:4 (98 chars) parent=frag-lex-805b03f284dcf364-002
    (4) The occupier must make a record of the calculations and how the final figures were arrived at.
```

Exit code `0` on pass, `1` when any expected locator is missing.

Fragment ids and parent ids vary between fixture, live intake, and export — only locators are stable acceptance criteria.

## Tests

| Layer | Path |
|-------|------|
| Python intake + verification | `law-proposition-extractor/tests/unit/test_regulation_paragraph_fragmentation_verification.py` |
| Python adapter smoke | `law-proposition-extractor/tests/unit/test_legislation_gov_uk_adapter.py` (`test_legislation_adapter_emits_regulation_and_article_paragraph_fragments`) |
| Review Workbench resolution | `law-proposition-extractor/apps/web/lib/context-locator-resolution.test.ts` |
| Offline CLML fixture (simplified) | `law-proposition-extractor/tests/fixtures/regulation_paragraph_fragmentation/wsi_2021_77_regulation_36.xml` |
| Live-shaped CLML fixture | `law-proposition-extractor/tests/fixtures/regulation_paragraph_fragmentation/wsi_2021_77_regulation_36_live_clml.xml` |

Run:

```bash
cd law-proposition-extractor
uv run --package law-proposition-extractor-pipeline pytest tests/unit/test_regulation_paragraph_fragmentation_verification.py -q
cd apps/web && npm test -- context-locator-resolution.test.ts
```

## Web app: test refreshed fragments before full export regeneration

**Yes — with a surgical `source_fragments.json` swap.**

The Review Workbench and Law Statements explorer resolve context locators against live `source_fragments` rows from `GET /ops/source-fragments` (`OperationalStore` reads the export root). They do **not** need regenerated propositions, law statements, or divergence artifacts to validate `regulation 36(4)` exact resolution.

Workflow:

1. Run source intake only (or `verify-regulation-paragraph-fragments --case …`) to produce refreshed structural fragments.
2. Replace `source_fragments.json` in the target export directory (and the matching run artifact file under `runs/<run>/artifacts/artifact-*-source-fragments.json` if the UI filters by run).
3. Point the API `operations_export_dir` / web `NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_OPS_EXPORT_DIR` at that export.
4. Open Review Workbench / Law Statements for a row citing `regulation 36(4)` — resolution should be **exact** on `regulation:36:paragraph:4`.

Caveats:

- Proposition `fragment_locator` / `source_fragment_id` links may still point at pre-refresh ids until extraction is re-run; context resolution uses **locator strings**, not proposition fragment ids.
- Fragment **ids** change when re-ingesting (suffix renumbering); do not assert on `frag-lex-*-NNN` in the UI after a fragment tree expansion.
- Law statement `standalone_status` / export-side resolution metadata stays stale until statement export is regenerated; the workbench recomputes resolution client-side from refreshed fragments.

## Related

- Root-cause report: `law-proposition-extractor/docs/regulation-36-4-resolution-report.md`
- Structural builder: `law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline/sources/adapters.py` (`_build_legislation_structural_fragments`)
- Locator resolution: `law-proposition-extractor/apps/web/lib/context-locator-resolution.ts`
