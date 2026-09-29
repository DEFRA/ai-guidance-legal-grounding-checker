# Generated assets inventory

This is the canonical map of every generated docs asset: where the source lives, where the rendered output lands, how to regenerate it, and whether the rendered output is committed.

## Commit policy

- Source assets are authoritative.
- Generated assets under `docs/assets/generated/` are **committed** for review and distribution alongside their sources.
- Do **not** hand-edit anything under `docs/assets/generated/`. Edit the source and regenerate.
- Regenerate before opening a PR that touches a source asset.
- A clean checkout should already include up-to-date generated outputs.

Regeneration commands:

- `just diagrams` — architecture D2 diagrams to SVG
- `just generate-explainability-diagrams` — explainability D2 suite to SVG (also via `just generate-explainability-docs`)
- `just infographics` — infographic SVG sources to generated SVG + PNG
- `just decks` — Marp deck markdown to HTML + PDF + PPTX
- `just infographic-context` — canonical context bundle for image prompts
- `just assets` — architecture diagrams + infographics + decks + context
- `just docs-refresh` — explainability docs/diagrams + assets + `mkdocs build`

## Diagram assets (D2 -> SVG)

| Source | Generated output | Committed | Role | Status |
| --- | --- | --- | --- | --- |
| `docs/assets/diagrams/core-workflow.d2` | `docs/assets/generated/diagrams/core-workflow.svg` | yes | derivative | current |
| `docs/assets/diagrams/technical-architecture.d2` | `docs/assets/generated/diagrams/technical-architecture.svg` | yes | derivative | current |
| `docs/assets/diagrams/temporal-audit.d2` | `docs/assets/generated/diagrams/temporal-audit.svg` | yes | derivative | current |
| `docs/assets/diagrams/pipeline-overview-v2.d2` | `docs/assets/generated/diagrams/pipeline-overview-v2.svg` | yes | derivative | current |
| `docs/assets/diagrams/artifact-map.d2` | `docs/assets/generated/diagrams/artifact-map.svg` | yes | derivative | current |
| `docs/assets/diagrams/fragment-selection-modes.d2` | `docs/assets/generated/diagrams/fragment-selection-modes.svg` | yes | derivative | current |
| `docs/assets/diagrams/extraction-repair-flow.d2` | `docs/assets/generated/diagrams/extraction-repair-flow.svg` | yes | derivative | current |
| `docs/assets/diagrams/proposition-review-workflow.d2` | `docs/assets/generated/diagrams/proposition-review-workflow.svg` | yes | derivative | current |
| `docs/assets/diagrams/explainability/law-proposition-extractor-system-map.d2` | `docs/assets/generated/diagrams/explainability/law-proposition-extractor-system-map.svg` | yes | derivative | current |
| `docs/assets/diagrams/explainability/source-to-statement-pipeline.d2` | `docs/assets/generated/diagrams/explainability/source-to-statement-pipeline.svg` | yes | derivative | current |
| `docs/assets/diagrams/explainability/legal-structure-data-model.d2` | `docs/assets/generated/diagrams/explainability/legal-structure-data-model.svg` | yes | derivative | current |
| `docs/assets/diagrams/explainability/source-version-and-effects.d2` | `docs/assets/generated/diagrams/explainability/source-version-and-effects.svg` | yes | derivative | current |
| `docs/assets/diagrams/explainability/article-49a-walkthrough.d2` | `docs/assets/generated/diagrams/explainability/article-49a-walkthrough.svg` | yes | derivative (fixture-generated D2) | current |
| `docs/assets/diagrams/explainability/divergence-workflow.d2` | `docs/assets/generated/diagrams/explainability/divergence-workflow.svg` | yes | derivative (mixed status block) | current |

Architecture diagrams: regenerate with `just diagrams` (clears top-level `generated/diagrams/*.svg` only). Explainability suite: regenerate with `just generate-explainability-diagrams`.

## Infographic assets (SVG source -> SVG + PNG)

Infographic SVGs are hand-authored and committed as the authoritative source. Generated outputs are a verified copy of the source and a raster PNG for stakeholder use.

| Source | Generated SVG | Generated PNG | Committed | Role | Status |
| --- | --- | --- | --- | --- | --- |
| `docs/assets/infographics/pipeline-overview.svg` | `docs/assets/generated/infographics/pipeline-overview.svg` | `docs/assets/generated/infographics/pipeline-overview.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/artifact-map.svg` | `docs/assets/generated/infographics/artifact-map.svg` | `docs/assets/generated/infographics/artifact-map.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/extraction-repair-flow.svg` | `docs/assets/generated/infographics/extraction-repair-flow.svg` | `docs/assets/generated/infographics/extraction-repair-flow.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/fragment-selection-modes.svg` | `docs/assets/generated/infographics/fragment-selection-modes.svg` | `docs/assets/generated/infographics/fragment-selection-modes.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/review-governance-workflow.svg` | `docs/assets/generated/infographics/review-governance-workflow.svg` | `docs/assets/generated/infographics/review-governance-workflow.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/equine-staged-corpus-roadmap.svg` | `docs/assets/generated/infographics/equine-staged-corpus-roadmap.svg` | `docs/assets/generated/infographics/equine-staged-corpus-roadmap.png` | yes | source (SVG) + derivative (PNG) | current |
| `docs/assets/infographics/run-quality-explainer.svg` | `docs/assets/generated/infographics/run-quality-explainer.svg` | `docs/assets/generated/infographics/run-quality-explainer.png` | yes | source (SVG) + derivative (PNG) | current |

Regenerate with `just infographics`. The script clears generated SVG/PNG outputs before each run. PNG rendering requires `rsvg-convert` (install via `brew install librsvg`); if absent, only the SVG copy is produced.

The companion text specs `docs/assets/infographics/pipeline-overview.md` and `docs/assets/infographics/prompt-template.md` document authoring intent and remain useful when refining the SVGs or hand-driving an external design tool.

### Infographic polished variants (externally authored)

These are approved, hand-authored polished assets stored beside infographic sources. They are committed as source assets and are not regenerated by `just infographics`.

| Asset | Committed | Role | Status |
| --- | --- | --- | --- |
| `docs/assets/infographics/overview-polished.png` | yes | polished source variant (external) | current |

## Deck assets (Marp markdown -> HTML + PDF + PPTX)

| Source | HTML | PDF | PPTX | Committed | Role | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `docs/assets/decks/law-proposition-extractor-stakeholder-overview.md` | `docs/assets/generated/decks/law-proposition-extractor-stakeholder-overview.html` | `docs/assets/generated/decks/law-proposition-extractor-stakeholder-overview.pdf` | `docs/assets/generated/decks/law-proposition-extractor-stakeholder-overview.pptx` | yes | derivative | current |
| `docs/assets/decks/law-proposition-extractor-technical-architecture.md` | `docs/assets/generated/decks/law-proposition-extractor-technical-architecture.html` | `docs/assets/generated/decks/law-proposition-extractor-technical-architecture.pdf` | `docs/assets/generated/decks/law-proposition-extractor-technical-architecture.pptx` | yes | derivative | current |
| `docs/assets/decks/law-proposition-extractor-operator-workflows.md` | `docs/assets/generated/decks/law-proposition-extractor-operator-workflows.html` | `docs/assets/generated/decks/law-proposition-extractor-operator-workflows.pdf` | `docs/assets/generated/decks/law-proposition-extractor-operator-workflows.pptx` | yes | derivative | current |

Regenerate with `just decks`. The script clears the generated decks directory before each run.

## Infographic prompt context (canonical bundle)

| Source | Generated output | Committed | Role | Status |
| --- | --- | --- | --- | --- |
| `docs/canonical/project-state.md`, `docs/canonical/roadmap.md`, `docs/canonical/audiences.md`, `docs/canonical/visuals.md` | `docs/assets/generated/context/infographic-prompt-context.md` | yes | derivative | current |

Regenerate with `just infographic-context`. This is the canonical bundle to paste into external image/design tools when authoring a polished infographic (the SVG infographics above remain the in-repo source-of-truth).

## What is not in this inventory

- Run/export artifacts under `dist/static-report/` — those are run outputs, not docs assets. See `docs/reference/artifacts.md`.
- API documentation rendered by MkDocs — produced by `just build-docs`, output under `site/` (uncommitted).
- Screenshots — none are tracked here today; add them as `docs/assets/screenshots/<topic>/<name>.png` with a row in this inventory if/when introduced.

## Authoritative source notes

- Diagram source files (`*.d2`) are authoritative; if a generated SVG looks wrong, fix the D2 source, not the SVG.
- Infographic SVG sources are authoritative; the generated copy and PNG are deterministic derivatives.
- Deck markdown is authoritative; HTML/PDF/PPTX are deterministic Marp renders.
- Canonical context inputs (`docs/canonical/*.md`) are authoritative; the prompt context bundle concatenates them and is regenerated, not edited.
