# Review governance

## Purpose

Law Proposition Extractor outputs are review datasets until humans accept them through governance workflows.

- Extraction output is not automatically legally approved.
- A lint/quality pass indicates artifact/quality-gate integrity, not legal approval.
- `pass_with_warnings` can still be operationally acceptable if warnings are reviewed and managed.
- `guidance-ready` is a promoted state after review; it is not default output.

![Proposition review governance workflow diagram](../assets/generated/diagrams/proposition-review-workflow.svg)

Diagram source: `docs/assets/diagrams/proposition-review-workflow.d2` (generated SVG may be absent in a clean checkout; run `just diagrams`).

## Reviewable artifact types

Current code/UI supports pipeline review decisions on these artifact types:

- `proposition`
- `structured_proposition_display` (structured proposition view layer in UI)
- `proposition_scope_links`
- `proposition_completeness_assessment`
- `proposition_extraction_trace`
- `source_target_link`
- `source_categorisation_rationale`
- `source_inventory_row`

Notes:

- Divergence assessments/findings currently have run review artifacts (`review_decisions`) and statuses, but they are not yet part of the same formalized `pipeline_review_decisions` effective-view set.
- If a type is not listed above, treat it as planned/not yet formalized for pipeline review decisions.

## Decision values

### Pipeline review decisions (`pipeline_review_decisions.json`)

Supported decision values (validated by code/API):

- `approved`
- `rejected`
- `needs_review`
- `overridden`
- `deferred`

### Legacy run review status values (`review_decisions` artifacts and domain enums)

Domain `ReviewStatus` includes values such as:

- `proposed`
- `needs_review`
- `accepted`
- `accepted_with_edits`
- `rejected`
- `needs_more_sources`
- `superseded`

Use the pipeline decision set when working with `add-review-decision` and `/ops/*pipeline-review-decisions*`.

## Persistence model

Pipeline review decisions are append-only:

- each row is keyed by `id`
- rows target `artifact_type` + `artifact_id`
- optional `applies_to_field` narrows scope to a specific field
- optional `supersedes_decision_id` marks a prior row superseded
- effective decision resolves as latest non-superseded row for artifact (+ field scope)

Decision row fields include:

- `artifact_type`, `artifact_id`, `decision`
- `reviewer`, `reviewed_at`, `reason`
- `replacement_value` (for `overridden` flows when applicable)
- `evidence`, `metadata`
- `applies_to_field`, `supersedes_decision_id`, optional explicit `decision_id`

Scope behavior:

- decisions are run-scoped by `run_id`
- persisted in export artifacts (`pipeline_review_decisions.json`) and mirrored into run artifact metadata/manifests

## CLI and API

### CLI

- `add-review-decision` (**mutating**)  
  Append one pipeline review decision row.  
  Important options: `--artifact-type`, `--artifact-id`, `--decision`, `--run-id`, `--reviewer`, `--reason`, `--applies-to-field`, `--supersedes-decision-id`, `--decision-id`, `--export-dir`.

- `list-review-decisions` (**read-only**)  
  Query pipeline review decision rows.  
  Important options: `--run-id`, `--artifact-type`, `--artifact-id`, `--decision`, `--export-dir`.

- `list-run-review-decisions` (**read-only**)  
  List legacy run review decision artifact rows (`review_decisions`) for a run.

### API

- `GET /ops/pipeline-review-decisions` (**read-only**)  
  Filter/query pipeline review decisions by `run_id`, `artifact_type`, `artifact_id`, `decision`.

- `POST /ops/runs/{run_id}/pipeline-review-decisions` (**mutating**)  
  Append one pipeline review decision row.  
  Key request fields: `artifact_type`, `artifact_id`, `decision`, optional `reviewer`, `reason`, `replacement_value`, `evidence`, `applies_to_field`, `supersedes_decision_id`, `metadata`, `decision_id`.

- `GET /ops/runs/{run_id}/review-decisions` (**read-only**)  
  Return run review decision artifacts (`review_decisions`) for that run.

## UI workflow

### Proposition Explorer

- exposes review layers per proposition row (raw, structured view, scope links, completeness)
- writes decisions through `POST /ops/runs/{run_id}/pipeline-review-decisions`
- reads persisted decisions from `GET /ops/pipeline-review-decisions`
- displays current effective status per layer (generated/approved/rejected/needs_review/etc.)

### Operations Inspector

- provides run/source/divergence inspection panels
- surfaces review decision data from run artifacts and `/ops` endpoints

Current limitation:

- review decisions do not by themselves constitute legal sign-off; they are governance metadata to support operator/legal review workflows.

## Guidance-ready promotion

Current implemented measurement is most explicit in equine coverage workflows:

- proposition review status must be accepted (`accepted` or `accepted_with_edits`)
- extraction trace confidence must be `high`
- completeness must not be `fragmentary`

This produces `guidance_ready` and `reason_if_not_guidance_ready` fields in equine proposition coverage artifacts.

Not yet a formal legal approval workflow:

- there is no global, legally binding approval engine in code that auto-certifies all outputs as legally approved.

### Recommended policy (operator/legal governance; not enforced globally)

Promote to guidance-ready only when:

1. proposition decision is accepted
2. structured display decision is accepted
3. scope-link decision is accepted (or deferred with explicit reason)
4. completeness is not fragmentary unless explicitly reviewed/accepted
5. extraction trace low-confidence cases are reviewed and resolved
6. source/citation traceability is present
7. no unresolved repairable extraction failure affects the proposition

## Worked example pattern

Generic staged-corpus pattern:

1. extraction produces proposed propositions
2. lint returns `pass_with_warnings`
3. reviewer marks rows as approved/rejected/needs_review (and overrides/deferred where needed)
4. reload/list decisions to verify persisted governance state
5. only accepted/reviewed rows become candidates for guidance-ready promotion

## Relationship to roadmap

Review governance is part of current v1/v1.5 quality foundations and is a dependency for future guidance/tooling integration. Treat current implementation as operational governance scaffolding, not final legal workflow automation.
