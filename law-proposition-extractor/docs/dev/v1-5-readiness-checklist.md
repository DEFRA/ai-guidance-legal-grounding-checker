# v1.5 readiness checklist

Manual checks before treating the workbench as v1.5-ready.

## 1. Setup

- [x] API starts
- [x] Web starts
- [x] CORS configured or defaults work
- [x] Article 109 equine pilot can be exported
- [x] Understand [operations bundle vs registry](operations-state-reset.md): clearing **runs** drops export/analysis output while keeping registered sources; **clear all** resets registry JSON and wipes snapshot/derived caches

## 2. Proposition discovery

- [x] `/propositions` loads latest run
- [x] Scope filter works
- [x] Article grouping works
- [x] Primary scopes are visible
- [x] Contextual scopes hidden by default

## 3. Proposition readability

- [x] Structured view visible
- [x] Raw view available
- [x] Provision type visible
- [x] Completeness chip visible (Complete / Needs context / Fragmentary / Not assessed as applicable)
- [x] Source excerpt available
- [x] Trace available

## 4. Review workflow

- [ ] Raw extraction review persists
- [ ] Structured view review persists
- [ ] Scope links review persists
- [ ] Completeness review persists
- [ ] Reload preserves statuses

### How to check this

The page hierarchy is **Article section** → **Proposition** → **Source row** → **Review layers**. Use the **Review layers** `<details>` panel under each source row on `/propositions`: **pipeline review decisions apply to that source row**, not the whole article section.

Each panel lists **Raw extraction**, **Structured view**, **Scope links**, and **Completeness**. Set a distinct status per layer (approve / reject / needs_review), wait for **Review saved** (or confirm the inline summary updates), then **refresh the page**. The collapsed line under **Review layers** should still show those four statuses — that verifies persistence and reload.

Completeness chips elsewhere reflect assessment status (**Complete**, **Needs context**, **Fragmentary**) or **Not assessed** when no completeness assessment row is loaded for that proposition.

## 5. Quality / trust

- [x] `lint-export` passes or warnings are understood
- [x] Run quality summary visible
- [ ] Evidence/source trace is available for reviewed rows

### How to check this

**Run quality (UI):** With a run selected, open **Selected run snapshot** → **View run quality summary (JSON)** (browser JSON). Counts and `quality` status should match what the UI shows in the snapshot strip.

**Lint / export (CLI):** Full bundle lint is not served as a separate HTTP resource. From the repo, run:

```bash
uv run --package law-proposition-extractor-pipeline python -m law_proposition_extractor_pipeline lint-export --export-dir dist/static-report
```

(use the same export directory the API is configured to read). Parse warnings or treat them as understood before calling the release “green.”

**Source traces:** In the snapshot area, **View proposition extraction traces (JSON)** lists effective traces; per proposition, expand **Evidence** and use **view extraction trace** (or the JSON) to confirm trace text is present after you have reviewed rows.

## 6. Known limitations

These are accepted gaps for v1.5 — not blocking items if understood:

- Timeline UI is not implemented.
- Structured view is heuristic.
- Scope linking is deterministic and may need review.
- Article-level grouping is UI-only.
