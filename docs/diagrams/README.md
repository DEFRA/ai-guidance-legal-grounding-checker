# Diagrams (Guidance to Law Comparison)

Canonical **diagrams-as-code** for this repository (content-audit / Guidance to Law Comparison pipeline).

## Canonical format

**D2** is the normal source-of-truth format for project diagrams.

Use D2 for enduring views such as:

- C4-style architecture (system context, containers)
- end-to-end pipeline topology
- component / process flows
- data and proposition flows
- legal / source relationship diagrams
- divergence / amendment diagrams
- status / model diagrams

We are **not** adopting Structurizr. C4 remains a **modelling convention** for architecture diagrams only — D2 does not enforce C4 semantics.

Component-local D2 already exists under [`law-proposition-extractor/docs/assets/diagrams/`](../../law-proposition-extractor/docs/assets/diagrams/) (ADR-0003). That pipeline stays the source of truth for LPE internals; this tree is for **repo-level / cross-component** diagrams.

## Three layers (source → renders)

| Layer | Role | When to use |
| --- | --- | --- |
| `.d2` | Canonical editable source | Edit / review layout logic |
| `.svg` | Primary docs / repository render | Markdown embeds, GitHub, Cursor — crisp at any zoom |
| `.png` | Portable / shareable companion | **Slack**, Teams, email, slides, tools that do not preview SVG reliably |

```text
docs/diagrams/<area>/<name>.d2
docs/diagrams/generated/<area>/<name>.svg   ← docs default
docs/diagrams/generated/<area>/<name>.png   ← sharing companion
```

**SVG stays the documentation format.** Do not replace Markdown/SVG references with PNG merely because Slack cannot preview SVG. PNG is generated output for external sharing — not a second source of truth.

Generated **SVG and PNG are both committed** so collaborators can view and share without a local D2 install. Do not hand-edit under `generated/`.

## Why D2

One diagrams-as-code language for more than software boxes:

- application architecture
- end-to-end legal comparison pipeline
- source / instrument relationships
- proposition flows and matching / adjudication
- legal divergence and evidence / provenance
- status aggregation

Mermaid layout is too weak for those views (especially in Cursor preview).

## Layout (sources → generated)

```text
docs/diagrams/
  README.md                 ← this convention
  shared/                   ← optional shared D2 fragments (classes, etc.)
  architecture/             ← C1 / C2
  pipeline/                 ← end-to-end Guidance → Law process
  concepts/                 ← conceptual models (e.g. proposition comparison)
  legal-model/              ← source stack, divergence, amendments (as needed)
  data-model/               ← proposition/comparison status (as needed)
  generated/                ← committed SVG + PNG; mirror source relative paths
```

| Source | Generated |
| --- | --- |
| `docs/diagrams/<area>/<name>.d2` | `docs/diagrams/generated/<area>/<name>.svg` |
| same `.d2` | `docs/diagrams/generated/<area>/<name>.png` |

Taxonomy folders are created when a diagram lands — do not add empty stubs.

## C4 convention (architecture diagrams)

### C1 — System Context

Show: people / roles, Guidance to Law Comparison as one software system, material external systems, high-level relationships.

Do not show: internal containers, modules, functions, individual pipeline stages.

### C2 — Containers

Show: major runnable applications/services (pipeline steps), important stores, major externals, significant flows.

This is the locked canonical container view of the current Guidance → Law implementation. It groups runtime responsibilities rather than showing full execution order. Do not turn C2 into a component, class, or process diagram.

Model services are intentionally aggregated to the Guidance to Law Comparison software-system boundary for readability; that boundary is not a runtime container.

## Mermaid exception

Mermaid is acceptable only when **all** of these hold:

- the diagram is small and self-contained in Markdown
- layout quality is unimportant
- it is not a canonical architecture or legal-model view
- moving it to D2 would add cost without clarity

Prefer D2 when the diagram is part of the project’s enduring technical or legal model.

**Left as Mermaid for now (deliberate):**

| Location | Why leave |
| --- | --- |
| [`RUNBOOK.md`](../../RUNBOOK.md) compact stage-order sketch | Tiny operator aid; points at canonical D2 SVG above it |
| `law-discovery/docs/v1-process.md` | Component-local process sketch |
| LPE `docs/explainability/pipeline.md` | Explainability handbook; LPE has its own D2 suite |

**Canonical D2 process view:** [`pipeline/end-to-end.d2`](pipeline/end-to-end.d2) · prose [docs/architecture/pipeline.md](../architecture/pipeline.md).

**Conceptual model (generalisation direction):** [`concepts/proposition-comparison.d2`](concepts/proposition-comparison.d2) · prose [docs/architecture/proposition-comparison.md](../architecture/proposition-comparison.md).

**Migrated to D2:** C1/C2 under [`architecture/`](architecture/) — prose in [`docs/architecture/`](../architecture/).

## Visual conventions (lightweight)

Align with existing LPE D2 style ([`core-workflow.d2`](../../law-proposition-extractor/docs/assets/diagrams/core-workflow.d2)):

- `direction: down` (or `right`) at the top of the file
- shared `classes` for tiers / boundaries / externals (see [`shared/classes.d2`](shared/classes.d2))
- groups for logical boundaries; let D2 layout place nodes — avoid hand-positioning
- short arrow labels; no decorative styling that encodes no meaning
- external systems use the `external` class; the Guidance to Law Comparison system / steps use `system` / `step`

### Render defaults (`just diagrams`)

Same source, layout engine, theme, and padding for SVG and PNG:

| Option | Value | Notes |
| --- | --- | --- |
| `--theme` | `0` | Neutral light theme |
| `--pad` | `100` (C1/C2 use `140`) | Outer margin on C1/C2; inter-group corridors come from diagram structure |
| C1 ELK gaps | `--elk-nodeNodeBetweenLayers=180`, `--elk-edgeNodeBetweenLayers=100` | Spreads horizontal relationship routes / labels |
| C2 ELK gaps | `--elk-nodeNodeBetweenLayers=100`, `--elk-edgeNodeBetweenLayers=60` | Landscape container map spacing |
| `--layout` | `elk` for `architecture/` and `concepts/`; `dagre` for `pipeline/` | Same engine for both formats |
| SVG `--scale` | D2 default (`-1`) | Vector docs; fit-to-screen behaviour |
| PNG `--scale` | `1` | Portable companion for Slack/email/slides (no post-resize) |

PNG is produced via D2’s native Playwright export (not a separate SVG rasteriser). Playwright applies a **2× device-pixel ratio**, so `--scale=1` yields roughly **2× the SVG logical size** — enough to inspect text in Slack without multi‑MB 4× rasters. The same deterministic scale is used for every diagram.

## Regenerate

From the **repository root**:

```bash
brew install d2   # once, if needed
just diagrams
```

Requires `d2` on `PATH`. The recipe fails clearly if `d2` is missing.

**PNG export** needs D2’s Playwright / Chromium dependencies (developer tooling only — not an application package). If PNG generation fails, the script prints recovery steps. Typical first fix:

```bash
unset PLAYWRIGHT_BROWSERS_PATH
npx --yes playwright install chromium
# Linux (missing OS libs):
npx --yes playwright install --with-deps chromium
```

If `d2` still 404s downloading a legacy `playwright-*-*.zip` driver, see the script’s error output for seeding `~/Library/Caches/ms-playwright-go/` (Playwright CDN retirement).

`just diagrams` must produce both SVG and PNG; it does **not** silently skip PNG.

LPE-only diagrams (unchanged):

```bash
cd law-proposition-extractor && just diagrams
# explainability suite:
cd law-proposition-extractor && just generate-explainability-diagrams
```

## Related

- Architecture prose: [`docs/architecture/`](../architecture/)
- LPE diagram assets + ADR-0003: [`law-proposition-extractor/docs/assets/diagrams/README.md`](../../law-proposition-extractor/docs/assets/diagrams/README.md) · [`adr-0003-d2.md`](../../law-proposition-extractor/docs/decisions/adr-0003-d2.md)
- LPE asset generation: [`law-proposition-extractor/docs/process/asset-generation.md`](../../law-proposition-extractor/docs/process/asset-generation.md)
