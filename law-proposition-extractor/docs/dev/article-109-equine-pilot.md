# Article 109 equine pilot (dev/demo)

Use this workflow to load **`examples/pilot_reg_2016_429_art109_equine.json`** into the **same bundle directory** the API serves (`OPERATIONS_EXPORT_DIR`), then browse propositions without hand-picking paths like `dist/pilot-art109-equine-v2`.

## Run the export

From the repo root:

```bash
just run-art109-equine-pilot
```

or:

```bash
./scripts/run-art109-equine-pilot.sh
```

- **Output directory:** `OPERATIONS_EXPORT_DIR` if set, otherwise **`dist/static-report`** (matches the API default in `law_proposition_extractor_api.settings`).
- **Fresh extraction:** the script passes a **temporary `--derived-cache-dir`** so derived proposition extraction is not replayed from an old cache. The case file also sets `strategy_versions.proposition_extraction` so cache keys stay aligned with structured-list extraction.

Point the API at the same directory:

```bash
export OPERATIONS_EXPORT_DIR=dist/static-report
just api
```

## UI

The script prints a **Propositions** URL with **`?scope=equine`**. In the app:

- Open **`/propositions?scope=equine`** — the scope filter is prefilled from the query string.
- Use **“Show equine propositions”** in the Filters card to apply the same filter and sync the URL.

If **no runs** appear on `/propositions`, the empty state includes the same **`just run-art109-equine-pilot`** hint.

## What to expect (validation only)

Not legal advice — pipeline/UI checks:

- A structured-list proposition for **Article 109 §1(d)(i)** (EU Art 109 source), with **`article:109:list:1-d-i`**-style locator.
- **Equine** scope link on proposition text matches: typically **explicit**, **direct**, **high** when “equine” / equine animals appear in the proposition text.
- **Extraction trace** `rule_id`: **`extract.heuristic.structured_list_items`** for those rows.
- **Review** actions on each proposition row append to **`pipeline_review_decisions.json`** for the served export directory.

Override web/API origins for printed links:

- **`JUDIT_WEB_ORIGIN`** (default `http://localhost:3000`)
- API base for your stack is separate — ensure **`OPERATIONS_EXPORT_DIR`** matches the running API.

## UX acceptance checklist (human workflow)

Ran end-to-end against `just run-art109-equine-pilot` → **`dist/static-report`**, API **`OPERATIONS_EXPORT_DIR`** aligned, web `npm run dev` (from `apps/web`).

| Step | Result |
|------|--------|
| `/propositions?scope=equine` loads; scope prefilled | OK |
| ≥1 proposition listed | OK (12 rows for `run-001` with equine filter) |
| **Art 109 §1(d)(i)** visible (EU Art 109 structured list) | OK |
| Row shows **label**, **proposition body**, **equine** scope link (direct / high), **`confidence:`** chip from effective extraction trace, **`review:`** chip | OK |
| **view extraction trace** → JSON includes **`rule_id`: `extract.heuristic.structured_list_items`** | OK |
| **view source fragment** → full Article 109 source text (scroll for §1(d)) | OK |
| **needs_review** on EU `pilot-eu-2016-429-art109:1-d-i:p004` → persists after full page reload | OK (`effective_status` / `review: needs_review` via API; append in `pipeline_review_decisions.json`) |

## UX friction / mitigations

1. **Next.js dev and `/propositions` 404** — On constrained macOS environments Watchpack can hit **EMFILE** (too many watched files). Next then compiles only fallback routes and **`/propositions` returns 404** even though `next build` lists the route. **Mitigation:** `apps/web` `npm run dev` sets **`WATCHPACK_POLLING=true`** so file discovery works without raising the global `ulimit`. If you still see 404-only dev behavior, raise `ulimit -n` or run `next build && next start` to confirm routes.
2. **Source row filter** — Options are long regulation titles; the filter control can show **truncated labels** (cosmetic; value is still correct).
3. **Duplicate-looking cards** — The pilot includes **EU and UK** retained snapshots of the same Article 109 list items, so **§1(a)–§1(d) appear twice** (six “109”-shaped blocks before Art 114 rows). Use **`source row`** filter (`pilot-eu-…` vs `pilot-uk-…`) when you care about one jurisdiction.
4. **Next.js dev on another port** — When **3000 is already in use**, `next dev` binds **3001** or the next free port. The browser origin must be allowed by the API’s CORS list or the Propositions page shows **Unable to reach operations API** / **Failed to fetch**. By default `law_proposition_extractor_api.settings` allows **`http://localhost` / `http://127.0.0.1` on ports 3000 and 3001**. For any other dev port, set **`CORS_ALLOWED_ORIGINS`** to a comma-separated list (replacing the default list), for example `http://localhost:3002,http://127.0.0.1:3002`. See `.env.example`.

## v1.5 review workflow acceptance (Article 109 equine pilot)

Run: **`just run-art109-equine-pilot`** (or `./scripts/run-art109-equine-pilot.sh`) so **`dist/static-report`** contains **`run-001`**. API: **`OPERATIONS_EXPORT_DIR`** matches that directory. Web: **`npm run dev`** from **`apps/web`** (default **`http://localhost:3000`**, or **3001** if 3000 is taken — see friction #4).

Recorded **2026-04-29**. UI checks used a **headless Chromium dump** of the hydrated page after CORS for **:3001** was enabled; persistence used **`GET/POST /ops/.../pipeline-review-decisions`** against **`127.0.0.1:8010`**.

**Hierarchy on `/propositions`:** Article section → Proposition → Source row → **Review layers**. Review decisions apply to that **source row**, not the whole article section.

**Completeness chips:** **Complete**, **Needs context**, **Fragmentary**, or **Not assessed** when no completeness assessment row exists for that proposition.

| # | Check | Result |
|---|--------|--------|
| 1 | **`/propositions?scope=equine`** loads **article-grouped** propositions (detail sections, not flat duplicate list) | **OK** — scope input prefilled `equine`; list shows grouped article headers; “Showing N proposition groups …” with filtered row count |
| 2 | **Primary** scope slugs shown in chips; **secondary** scopes not listed until **Show all scopes** | **OK** — “Show all scopes” appears where contextual/low-confidence links exist; default list is direct+high only (`partitionScopeLinksSorted` + `showAllScopes` default `false`) |
| 3 | **Provision type** visible in structured view | **OK** — e.g. “Provision type” / “Core rule” (and related fields) in structured card |
| 4 | **Review layers** panel **collapsed** by default (nested under each **Source row** in **Article section** → **Proposition** hierarchy) | **OK** — `<details>` for the review panel has no `open` attribute on initial render (12 panels for filtered rows); copy explains decisions apply to the **source row**, not the whole article section |
| 5 | Collapsed **summary line** lists **Raw · Structured · Scopes · Completeness** with status text | **OK** — compact line present; `needs_review` / `rejected` use emphasis classes |
| 6 | **Expand** exposes **four targets** with full labels + buttons | **OK** — each panel includes Raw extraction, Structured view, Scope links, Completeness rows (12×) |
| 7 | Set statuses (one row): Raw **approved**, Structured **needs_review**, Scopes **approved**, Completeness **approved** | **OK via API** — `POST /ops/runs/run-001/pipeline-review-decisions` per artifact (`proposition`, `structured_proposition_display`, `proposition_scope_links`, `proposition_completeness_assessment` with completeness **`artifact_id` = PCA row**, e.g. `pca-prop:4b9eca37be185550` for **`prop:4b9eca37be185550`**) |
| 8 | **Reload** then confirm four **independent** persisted statuses | **OK** — `GET /ops/pipeline-review-decisions?run_id=run-001` resolves latest decision per artifact; UI reads the same bundle |

Example row exercised: **`prop:4b9eca37be185550`** (EU **Article 109 §1(d)(i)**, equine **direct/high** scope link).

**CORS note:** `CORSMiddleware` uses **`settings.cors_allowed_origins`** (defaults above; override with **`CORS_ALLOWED_ORIGINS`**).
