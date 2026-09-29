# Asset generation workflow

Keep source files human-editable and generated outputs deterministic. Generated outputs are **committed** for review and distribution; see `docs/assets/generated-assets.md` for the full inventory and commit policy.

## Sources of truth

- **Architecture diagrams** — `docs/assets/diagrams/*.d2`
- **Explainability diagrams** — `docs/assets/diagrams/explainability/*.d2` (generate/check via `just generate-explainability-diagrams`)
- **Infographics** — `docs/assets/infographics/*.svg` (hand-authored SVG; companion `*.md` specs for narrative notes)
- **Decks** — `docs/assets/decks/*.md` (Marp markdown)
- **Infographic prompt inputs** — `docs/canonical/project-state.md`, `docs/canonical/roadmap.md`, `docs/canonical/audiences.md`, `docs/canonical/visuals.md`

## Generated outputs (committed)

- Diagrams - `docs/assets/generated/diagrams/*.svg`
- Infographics - `docs/assets/generated/infographics/*.svg` (verified copy) and `*.png` (rsvg-convert raster)
- Decks - `docs/assets/generated/decks/*.{html,pdf,pptx}`
- Infographic prompt context - `docs/assets/generated/context/infographic-prompt-context.md`

Do not hand-edit anything under `docs/assets/generated/`. Edit the source and regenerate.

## Regeneration commands

- Diagrams - `just diagrams`
- Infographics - `just infographics`
- Decks - `just decks`
- Infographic prompt context bundle - `just infographic-context`
- Full assets refresh - `just assets`
- Full refresh + docs build - `just docs-refresh`

## When to regenerate

### On every architecture or doc change

1. Update the relevant source file (D2 / SVG / Marp markdown / canonical state file).
2. Run `just assets` (or just the specific subcommand for the changed source).
3. Review the regenerated outputs under `docs/assets/generated/` before opening a PR.
4. Run `just build-docs` (or `just docs-refresh` for everything) and check the site renders cleanly.

### Before demos / stakeholder sessions

1. Run `just docs-refresh` to refresh all generated assets and rebuild the docs site.
2. If a polished image-model-rendered variant is needed, run `just infographic-context` and use `docs/assets/infographics/prompt-template.md` together with the regenerated context bundle.
3. Save any approved externally-generated images alongside the SVG source and document them in `docs/assets/generated-assets.md`.

## Tooling

- `d2` for diagrams (`brew install d2`).
- `rsvg-convert` for infographic PNG rasters (`brew install librsvg`).
- Marp CLI for decks (installed under `node_modules` via `npm install`).
- The `just` commands wrap shell scripts under `scripts/render_*.sh`.
