# Law Proposition Extractor polished infographic prompt template

Use this as a starting point for external image/design generation tools.

## Prompt

Create a polished infographic for **Law Proposition Extractor**, a source-first, proposition-first legal analysis workbench.

Use the canonical context from:

- `docs/assets/generated/context/infographic-prompt-context.md`

Generated assets may be absent in a clean checkout. Run `just docs-refresh` to regenerate them.

Hard constraints:

- Reflect current architecture accurately.
- Show `single_jurisdiction` as first-class and `divergence` as downstream.
- Include source registry and operations/audit surface.
- Include temporal history inspection for sources, propositions, and divergence findings.
- Represent v1 scope clearly and separate future layers.
- Keep terminology consistent with canonical files.
- Balance technical and non-technical audience needs.

Visual direction:

- Tone: polished, clear, trustworthy.
- Layout: one-page overview, logical left-to-right flow.
- Include: source registry -> proposition inventory -> optional divergence, ops/history layer, output bundle boundary, near-term roadmap.
- Prefer high-contrast, presentation-safe colors.

Output request:

- 16:9 slide-friendly variant
- social/poster variant
- editable source format if supported

Before finalizing, verify every claim against canonical files.
