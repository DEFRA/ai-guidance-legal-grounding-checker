# Effective law layers (propositions → relationships → guidance statements)

Law Proposition Extractor exports distinct layers for legal content. Each layer has a different job; do not collapse them in UI or Proposition Matcher handoff.

## A. Atomic propositions (`propositions.json`)

Source-faithful extracted statements from instrument fragments.

- One row per extracted proposition.
- Text and locators reflect what the extractor saw in the fragment.
- Cross-reference rows may be incomplete or context-dependent by design.
- **Do not** rewrite these into self-contained “laws” at export time.

## B. Proposition relationships (`proposition-relationships.json`)

Deterministic, reviewable edges between propositions and locators.

- Produced at export from `explicit_cross_reference_targets` (and related fields).
- Edge types include `text_references_locator` and `locator_resolves_to`.
- Same-source resolution only; ambiguous or missing targets stay explicit.
- No LLM calls; stable edge IDs for diffing and review.

Relationship / cross-reference propositions are **legal wiring instructions**: they say how provisions connect, not what the connected rule says. They should be used to resolve and enrich host or imported rules, not matched directly against GOV.UK guidance as primary law.

## C. Legal rule groups (`legal_rule_groups.json`)

Persisted proposition sets that share one structural source fragment (for example Article 49a paragraph 1 yielding two retained propositions).

- Built at export from retained/exported propositions only (post filter/dedupe).
- Membership is direct-fragment only: `source_fragment_id` must match the group fragment; no descendant or article-level aggregates.
- `group_basis` is currently `shared_source_fragment` only (not soft-duplicate or semantic similarity).
- Stable `rulegrp:` ids from `source_snapshot_id` + `source_fragment_id` + `canonical_locator` + basis.
- Additive/optional for older bundles; do not overload `proposition-relationships.json` for membership.
- Lookup helpers (`group_for_source_fragment`, `group_for_canonical_locator`) are source/snapshot-scoped for typed relationships.
- Source snapshots may record authority-supplied manifestation semantics (`manifestation_type`, resolved as-of dates) separately from Law Proposition Extractor amendment application. Recording `revised` does **not** mean Law Proposition Extractor verified outstanding effects or reconstructed historical lineage.

## C1. Source legal effects (`source_legal_effects.json`)

Additive inventory of amendment/change annotations and outstanding-effect metadata **explicitly present in the consumed legislation.gov.uk CLML**.

- Built from CLML `Commentary` / inline `Addition`·`Substitution`·`Repeal` markers and `UnappliedEffect` metadata — not from proposition text after extraction.
- Links effects to structural source fragments/locators (e.g. `article:49a:paragraph:1`) when the XML establishes that linkage.
- Records authority-reported status (`source_marks_outstanding`, `source_status_unknown`, …). Does **not** assert that Law Proposition Extractor applied an amendment.
- Affecting-instrument fields are copied from source citations only; `independent_consumption_status` is reconciled at export against the current run's SourceRecord / SourceSnapshot inventory (and optional source-register entries). Exact identity matches with a retained snapshot become `consumed_in_current_run`; register/intake hits without a snapshot become `present_in_source_register_but_not_consumed`; precise identifiers with no run hit become `not_matched`; insufficient identity or an unusable inventory remain `not_assessed`. Matching never fetches instruments, never uses title similarity, and never asserts that Law Proposition Extractor applied the effect.
- Aggregate `outstanding_effects_status` is `source_status_unknown` unless the consumed XML contains explicit `UnappliedEffects` metadata — revised manifestation alone never implies “no outstanding effects”.
- Distinct from manifestation evidence, legal rule groups, typed relationships, and proposition relationships.
- Optional on older bundles; empty inventories are valid.

## C2. Legal rule relationships (`legal_rule_relationships.json`)

Typed legal-semantic edges (`exception_to`, `triggered_by`) derived after locator resolution and legal rule groups.

- Built only from explicit high-confidence cues in retained proposition text (e.g. “shall not apply”, “in the cases referred to in”), associated with a specific reference — not from every resolved cross-reference.
- Direction: exception proposition `--exception_to-->` disapplied rule/group; obligation `--triggered_by-->` triggering cases/group.
- Prefer a unique `LegalRuleGroup` target; else a unique retained proposition on the resolved fragment. Never fan out to multiple members automatically at persistence time.
- Stable `legalrel:` ids; optional on older bundles.
- Consumed by effective-law statement composition (group targets expand one level into member required-context). Workbench surfaces typed relationships and required context through the law view and the “Why did Law Proposition Extractor produce this?” DecisionExplanation panel.
- Non-blocking diagnostics (`typed_relationship_target_ambiguous`, `typed_relationship_target_group_missing`, `typed_relationship_reference_not_uniquely_associated`) when a strong cue cannot safely emit an edge.

## D. Effective law statements (`effective_law_statements.json`)

Guidance-facing composed law bundles derived from propositions, locator relationships, legal rule groups, and typed legal rule relationships.

- `presentation_role` — whether a row is a guidance matching candidate, context connector, supporting definition, etc.
- `standalone_status` — whether the statement can stand alone for matching or needs host/imported context.
- `required_context` — locators and resolution status for unresolved or incorporated material, including typed kinds:
  - `applicable_exception` — incoming `exception_to` (group targets expand to direct members)
  - `exception_target` — outgoing `exception_to` (which rules the exception displaces)
  - `trigger_condition` — outgoing `triggered_by` (triggering cases / group members)
- Typed relationship context takes precedence over generic locator context for the same proposition; unrelated locator context (e.g. Article 14) is retained.
- Typed context entries carry auditable provenance (`relationship_id`, `relationship_type`, `relationship_direction`, `legal_rule_group_id`, `inherited_via_group`, `resolution_basis`, `inference_basis`, …).
- Conservative by default: prefer `context_dependent` or `relationship_only` over over-composition. Receiving resolved typed relationship context marks a previously `standalone` statement as `context_dependent`.
- Non-blocking composition diagnostics (e.g. `effective_law_relationship_group_member_missing`) when a persisted relationship cannot safely be applied.

This is the **broad derived law layer** for review and UI. It includes definitions, procedural context, and cross-reference wiring rows.

## E. Proposition Matcher law candidates (`proposition_matcher_law_candidates.json`)

Narrow **matching queue** for Proposition Matcher, derived from effective law statements without mutating propositions or the broad law layer.

- Includes only `presentation_role == "guidance_matching_candidate"`, excluding `relationship_only` and `fragmentary` standalone statuses.
- Excludes direct candidates for context connectors, supporting definitions, procedural/enforcement context, and debug rows.
- `context_dependent` and `partially_resolved` guidance candidates are included with `usable_with_context` status and risk flags when appropriate.
- Context connectors and definitions may still appear in `supporting_proposition_ids`, `required_context`, and `evidence` on included candidates.
- Proposition Matcher should match human-readable guidance claims against **candidates**, not raw `propositions.json`.
- `statement_text` is the canonical derived law statement (do not rewrite for matching).
- `matching_text` is deterministic retrieval/matching text assembled from title, statement, source/locator, territory (when determinable), required context, and connector context — no LLM paraphrase.
- Each candidate carries raw territorial metadata (`jurisdiction`, `source_jurisdiction`, `extent`, `territorial_application` when available) plus display fields `territory_labels` and `jurisdiction_label`. Display labels are derived deterministically from proposition territory fields, source inventory metadata, and conservative citation/title heuristics (for example WSI → Wales, SSI → Scotland). Labels may be omitted when evidence is weak.
- Proposition Matcher should use `territory_labels` / `jurisdiction_label` for retrieval and matching filters, and `matching_text` for candidate retrieval against GOV.UK guidance, but present `statement_text` as the legal statement to users. Provenance and source linkage remain source-based.
- `required_context` distinguishes **internal** locators (`regulation`, `schedule`, `paragraph` within the instrument) from **external** technical references (`BS 5502`, `RB209`, Fertiliser Manual, FACTS). External references use `resolution_status: external_reference` and are not resolved to propositions in Law Proposition Extractor (no web fetch). A bare `paragraph 7` parsed from BS wording is not emitted as an unresolved internal locator when it is part of an external standard cite.
- Proposition Matcher may use external references for matching and display; they are not missing internal law. Malformed external cites may still surface `needs_review`.
- **Locator labels** are provision-path-canonicalised for display and soft dedupe: SSAFO-style format variants (`paragraph:1(a)`, `…:subparagraph:a`, `…:list:1-a`) collapse to one key and one preferred structured display form. Raw fragment locators remain on `evidence.fragment_locators`.
- **Limb-only altitude**: when the same source+provision path yields both a chapeau echo (paren/`list:` encoding and/or “Subject to paragraph…” stem) and a structured limb, only the limb is emitted as a primary candidate. Suppressed chapeau text is folded into the winner’s `required_context` as `kind: "chapeau"`. Top-level `altitude_summary` reports `chapeau_suppressed_count` / `groups_collapsed`.
- **Same-source duplicates** (soft dedupe, Option B): candidates that share one `source_record_id`, the same normalized provision path, and the same `normalized_statement_text` are grouped with `dedupe` metadata (`duplicate_group_id`, `is_canonical`, `canonical_candidate_id`). All rows are retained; Proposition Matcher/UI should prefer `dedupe.is_canonical == true` for matching to avoid double-counting the same provision. Canonical selection is stable (best `candidate_status`, then lowest `bcand:` id).
- **Cross-jurisdiction equivalence** is not deduped: identical statement text across UKSI/WSI/SSI sources remains separate candidates for divergence and territory-aware matching.
- Top-level `duplicate_summary` reports how many same-source duplicate groups exist in the export.

### Proposition Matcher / guidance handoff

| Proposition kind | Typical `presentation_role` | Match to guidance? |
| --- | --- | --- |
| Obligation, prohibition, permission | `guidance_matching_candidate` | Yes, when `standalone_status` is `standalone` |
| Definition | `supporting_definition` | Supporting context only |
| Cross-reference / `relationship_reference` | `context_connector` | No — wiring only |
| Citation, commencement, extent | `procedural_or_enforcement_context` | Usually no |

Example: a proposition at `regulation 9(3)` that only states factors under `regulation 9(2)` include those in `regulation 4(2)` is a **context connector**, not a primary standalone law for guidance matching.

## Producer

`law_proposition_extractor_pipeline.effective_law.attach_effective_law_artifacts` runs during `export_bundle` (before `export_static_bundle`). Construction order:

1. proposition / locator relationships
2. legal rule groups
3. legal rule relationships
4. effective law statements (consumes groups + typed relationships)
5. Proposition Matcher law candidates
6. composition traces

Re-exporting a persisted run regenerates these derived artefacts without mutating `propositions.json`.
