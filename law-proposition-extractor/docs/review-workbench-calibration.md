# Review Workbench calibration guide

Read this before reviewing a batch. Aim for consistent verdicts across reviewers so exported JSON is useful for calibration and pipeline improvement.

## Purpose

The Review Workbench (`/statements`) evaluates **sampled effective law statements** from `effective_law_statements.json`.

You follow the provenance journey — **law fragment → propositions → composed statement → verdict** — and record structured judgements. Reviews persist in browser local storage and export as review JSON (schema v3) for aggregation on **Review analysis** (`/review-analysis`).

This is **evaluation data**, not legal sign-off. You are measuring how well the pipeline composed guidance-facing statements from extracted propositions and source text.

## Verdicts

Select one or more verdicts. **Accurate** is exclusive — choosing it clears other verdicts. Any issue verdict requires **severity** and supporting evidence (see [Draft vs complete](#draft-vs-complete)).

### Accurate

The statement correctly reflects the underlying source fragments and linked propositions for its `presentation_role` and `standalone_status`.

- Meaning is faithful; nothing important is missing or invented.
- Awkward phrasing alone is not inaccurate if the legal content is right.
- **Severity is not required** when accurate is the only verdict.

### Incomplete

The statement is **too thin or partial** relative to what the linked source material supports — material that *is* represented by propositions (or should be in the statement) is missing from the composed text.

**Mark evidence:**

- **Coverage gap here** on the law fragment where source text supports content absent from the statement, or
- Notes explaining what is missing.

Use when the pipeline had the pieces but composed an under-inclusive statement. Do not use for source text that never became a proposition (see **Missing propositions**).

### Overreaching

The statement **goes beyond** what the sources support — extra obligations, wrong scope, invented requirements, or propositions that should not contribute.

**Mark evidence:**

- **Wrong extraction** or **Should not exist** on the offending proposition(s), or
- Notes citing the fragment and what was over-claimed.

### Bad merge

Distinct legal ideas were **incorrectly combined** into one statement — unrelated obligations merged, wrong cross-reference resolution, or propositions that should stay separate.

**Mark evidence:**

- A composition-related **failure stage** (`composition`, `proposition normalisation`, or `context resolution`), or
- Notes naming which propositions should not have been merged.

### Missing propositions

Source text clearly contains extractable legal content but **no proposition was extracted** for it.

**Mark evidence:**

- **Missing proposition here** on the law fragment, or
- Notes quoting the source span that should have been extracted.

Use when the gap is upstream of composition (extraction), not when propositions exist but the statement omits them (use **Incomplete**).

## Severity

Required for any verdict that is not **only accurate**. Pick the highest level that applies.

| Severity | When to use |
| --- | --- |
| **Cosmetic** | Wording or presentation nit; legal meaning unchanged. Unlikely to affect matching or reader understanding. |
| **Minor** | Small gap or error; a careful reader would probably recover the right meaning from surrounding context. |
| **Significant** | Would mislead a reader, break guidance matching, or omit/add a requirement that matters for the statement's role. |
| **Critical** | Materially wrong law, unsafe for guidance use, or would cause serious compliance misunderstanding. |

When torn between two levels, prefer the **higher** severity if the statement could reach Proposition Matcher candidates or external guidance comparison.

## Failure stages

Mark every stage that contributed to the problem (multi-select). These feed failure-pattern analysis.

| Stage | Typical cause |
| --- | --- |
| **Source selection** | Wrong or missing instrument/fragment in the corpus for this statement. |
| **Proposition extraction** | Garbled, partial, or absent extraction from otherwise good source text. |
| **Proposition normalisation** | Normalisation changed meaning, scope, or modality. |
| **Context resolution** | Cross-references, host rules, or incorporated material resolved incorrectly. |
| **Composition** | Wrong merge/split of propositions into the statement. |
| **Statement wording** | Final statement phrasing distorts meaning even if propositions are OK. |
| **Proposition Matcher suitability** | Statement should or should not be in the Proposition Matcher matching queue given its role/status. |

**Bad merge** reviews should include at least one of: composition, proposition normalisation, context resolution.

## Good review notes

Notes should be **brief, specific, and actionable** — enough for another reviewer or an engineer to find the issue without re-deriving your reasoning.

**Good examples:**

- `Incomplete — reg 4(2) storage duty in fragment frg:abc not reflected in statement; coverage gap marked.`
- `Overreaching — prop:def marked should_not_exist; no permission in source, only a definition.`
- `Bad merge — reg 7 notification and reg 12 record-keeping merged; should be two statements.`
- `Missing propositions — fragment frg:xyz lists three conditions; none extracted.`
- `Accurate after checking WSI extent; standalone obligation matches reg 3(1) excerpt.`

**Avoid:**

- `Looks wrong` (no locator, no stage, no severity rationale)
- Long narrative essays — use fragment/proposition marks first, notes second

## Draft vs complete

The workbench shows **Review quality: complete** or **draft**.

| Status | Meaning |
| --- | --- |
| **Unreviewed** | No verdict selected. |
| **Draft review** | Started but missing required fields (verdict, severity, or evidence for issue verdicts). |
| **Complete review** | Ready for export as evaluation data. |

**Leave as draft when:**

- You need to check the full instrument PDF or a colleague's view.
- You are mid-batch and will return to the statement.
- You are unsure of severity or failure stage — add a partial note and finish later.
- Required evidence is not yet marked (the panel lists what is missing).

You **can** export drafts (filename includes `-includes-draft`); Review analysis can include or exclude them via filters. Prefer **complete** reviews for calibration metrics.

## Quick workflow

1. Read the statement and quality chips (warnings, confidence, proposition count).
2. Walk **Law → Propositions → Statement**; compare excerpt to composed text.
3. Select verdict(s), severity, failure stages, and fragment/proposition marks.
4. Confirm **complete review** before moving on in a calibration batch.
5. Export JSON when the batch is done; import on Review analysis.

## Source excerpt spacing (display only)

The workbench repairs common missing-space artefacts in **source/legal excerpts** at display time (for example `181The` → `181 The`, `amake` → `a make`, `3.The` → `3. The`). This applies everywhere excerpts are shown: **Used to build this statement**, the provenance journey **Law** panel, proposition evidence previews, composition source excerpts, and expanded assessment-context fragments.

It does **not** change:

- the composed **statement text** under review,
- **proposition text** (model output),
- exported review JSON,
- or raw source records / dedupe keys in run artifacts.

After pulling UI changes that affect excerpt display, a **browser hard refresh** (or reopening the tab) is enough — the repair runs when views are built from the current run API responses. You do **not** need to regenerate `effective_law_statements.json` or other export artifacts for spacing fixes. If the dev server was already running when you pulled, restart `npm run dev` so Next.js picks up the updated client bundle; stale **review** data in browser local storage only affects verdicts, not excerpt rendering.
