I want to generate a polished, stakeholder-facing one-page infographic for this repo.

Do a READ-ONLY audit of this repository and produce an “Infographic Evidence Pack” that contains all information needed for an external designer/LLM to create a high-level visual overview.

Important:
- Do not edit files.
- Do not generate images.
- Do not call external APIs or LLMs.
- Do not require secrets.
- Do not rely only on README claims.
- Inspect docs, code, tests, examples, package scripts, configs, diagrams, generated assets, and existing visual material.
- Prefer evidence from implementation and tests over aspirational docs.
- Clearly distinguish implemented behaviour from planned/aspirational behaviour.
- If a fact is uncertain, mark it as uncertain.

Goal of the future infographic:
A shiny, impressive, stakeholder-friendly one-pager showing how this system works at a high level:
input material → ingestion/normalisation → processing/transformation → structured outputs → analysis/comparison/reporting.
Ignore detailed review/governance/approval workflows unless they are central to the product narrative.

Please produce the evidence pack with the following sections.

# 1. Project identity

Extract:
- project name
- product/system name if different
- one-sentence summary
- 3–5 sentence plain-English explanation
- target audience/stakeholders
- current maturity: prototype / active development / production-like / experimental
- what the system is definitely not

Include evidence paths.

# 2. High-level system narrative

Describe the repo’s actual end-to-end workflow in 5–8 stages.

For each stage include:
- stage name
- plain-English explanation
- input
- output
- relevant code/docs paths
- whether implemented, partial, or planned

Example format:

1. Source material
2. Ingestion / capture
3. Normalisation / parsing / fragmentation
4. Extraction / transformation
5. Structured inventory / database / dataset
6. Analysis / reasoning / comparison
7. Outputs / reports / UI / API

Adjust these names to fit the repo.

# 3. Core concepts and vocabulary

Identify the project’s own vocabulary.

For each concept include:
- canonical term
- simple definition
- where it appears in code/docs
- suggested short label for an infographic

Look for concepts like:
- source
- document
- snapshot
- fragment
- proposition
- entity
- record
- event
- workflow
- job
- trace
- artifact
- analysis
- comparison
- report
- dataset
- registry
- pipeline
- run

Only include concepts that actually exist in this repo.

# 4. Inputs and outputs

Create two tables.

## Inputs
For each input type:
- name
- examples
- format
- where it enters the system
- evidence paths

## Outputs
For each output type:
- name
- examples
- format
- where produced
- who consumes it
- evidence paths

Include files/artifacts/API/UI outputs if present.

# 5. Architecture / pipeline map

Inspect implementation and docs to identify:
- main packages/apps/services
- key modules
- data flow
- APIs
- CLIs
- background jobs
- persistence/storage
- generated artifacts
- UI pages/components if any

Return:
- a concise architecture summary
- a bullet list of main components
- a Mermaid or ASCII diagram of the actual flow
- evidence paths for each major component

# 6. Existing diagrams / visuals / assets

Search for:
- diagrams
- infographics
- images
- SVG/PNG/PDF assets
- D2 files
- Mermaid diagrams
- Excalidraw/Figma references
- generated asset directories
- screenshots
- slide decks

Use searches like:
- infographic
- diagram
- overview
- architecture
- pipeline
- workflow
- mermaid
- d2
- svg
- png
- deck
- presentation
- generated

Report:
- file path
- purpose
- whether it appears current/stale
- whether it should influence the new infographic
- any existing wording or visual style to preserve

# 7. Claims vs implementation check

Create a table:

| Claim / topic | Where claimed | Implementation evidence | Status | Notes |

Statuses:
- accurate
- partially accurate
- stale
- aspirational
- contradicted
- uncertain

Focus on claims that would affect the infographic narrative.

# 8. Recommended infographic story

Based on the audit, propose the best one-page infographic structure.

Include:
- recommended title
- recommended subtitle
- 5–8 visual stages
- short copy for each stage
- icons/metaphors for each stage
- important callouts
- things to avoid showing
- any terminology to avoid because it is too technical or misleading

Keep this stakeholder-facing, not engineering-heavy.

# 9. Suggested visual hierarchy

Recommend:
- primary flow
- secondary callout panels
- footer/outcome band
- whether the graphic should be left-to-right, top-to-bottom, radial, layered, or split-path
- where analysis/comparison/reporting should appear
- whether to show one or multiple input documents
- whether to show branching outputs

# 10. Design cues from repo

Extract:
- brand/product colours if present
- typography or UI style if obvious
- existing logo/icon references
- screenshots or UI style that should influence the infographic
- tone: formal/legal/technical/friendly/enterprise/etc.

If no design system exists, say so.

# 11. Stakeholder copy block

Write polished, short copy suitable for direct use in an infographic:

- title
- subtitle
- stage labels
- one-line stage captions
- 3–5 benefit chips
- 3 core principles
- short footer sentence

Avoid jargon unless it is core to the product.

# 12. Regeneration / repo integration recommendation

Suggest how this infographic should live in the repo.

Include:
- proposed source brief path
- proposed generated asset path
- proposed deterministic diagram source path if useful
- whether D2, Mermaid, SVG, or AI-generated PNG is best
- suggested Makefile/Justfile/package script target if the repo has such tooling
- docs pages where it should be embedded

Do not implement this; just recommend.

# 13. Missing information / questions

List anything you could not determine from the repo but that would help generate a better infographic.

# Output format

Return a single markdown report titled:

# Infographic Evidence Pack

Make it concise but complete.
Use repo-relative file paths as evidence.
Do not include huge code excerpts.
Do not edit the repo.