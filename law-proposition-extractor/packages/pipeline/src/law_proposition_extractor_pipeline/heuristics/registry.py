"""Code-declared registry of material Law Proposition Extractor heuristics.

Source of truth is this module — not YAML or Markdown. Rule versions describe
heuristic semantics, not Git commits. Convention: integer string versions
(``\"1\"``, ``\"2\"``, …).

Skip-reason mapping policy
--------------------------
Ordinary base-selection skips that share one implementation path
(``_select_fragment_for_extraction``) are registered as **separate** stable
rules when each skip code is a named, material exclusion operators care about:

- ``selection.skip_non_operative`` ← ``skipped_non_operative`` / ``non_operative``
- ``selection.skip_too_short`` ← ``skipped_too_short`` / ``too_short``
- ``selection.skip_required_only_mode`` ← ``skipped_not_required_in_required_only_mode``

``skipped_no_focus_match`` is intentionally **not** registered: in
``required_plus_focus`` mode it fires for almost every non-matching fragment and
would flood the decision artifact. Emission policy (see selection_explanations)
only records exclusions where a named rule materially prevented extraction after
a fragment was eligible for consideration under the configured mode.

Structured-list reconciliation rules (extraction stage) record deterministic
terminal composition, duplicate suppression, distinct same-path retention, and
stem/branch-only rejection. Method remains deterministic even when an input row
originated from an LLM extraction call.

Classification and relationship rules record deterministic legal-effect
assignment and typed ``exception_to`` / ``triggered_by`` inference (including
LegalRuleGroup target preference). Grouping and effective-law rules record
shared-fragment LegalRuleGroup construction and typed required-context
expansion (including typed-over-generic locator precedence). Extracted fields
such as ``provision_type`` may be inputs; decision method remains deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from law_proposition_extractor_domain import DecisionStage, HeuristicMethod

REGISTRY_VERSION = "1"

# Stable rule IDs for the selection explainability slice.
RULE_REQUIRED_LOCATOR = "selection.required_locator"
RULE_FOCUS_TERM_MATCH = "selection.focus_term_match"
RULE_SKIP_NON_OPERATIVE = "selection.skip_non_operative"
RULE_SKIP_TOO_SHORT = "selection.skip_too_short"
RULE_SKIP_REQUIRED_ONLY_MODE = "selection.skip_required_only_mode"
RULE_PREFER_REQUIRED_CHILDREN = "selection.prefer_required_children"
RULE_PREFER_REQUIRED_ANCESTOR = "selection.prefer_required_ancestor"
RULE_STRUCTURAL_OVERLAP_UNRESOLVED = "selection.structural_overlap_unresolved"

# Stable rule IDs for structured-list reconciliation (extraction stage).
RULE_COMPOSE_TERMINAL_LEAF = "structured_list.compose_terminal_leaf"
RULE_SUPPRESS_DUPLICATE_TERMINAL = "structured_list.suppress_duplicate_terminal"
RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS = "structured_list.preserve_distinct_terminal_claims"
RULE_REJECT_NON_TERMINAL_ROW = "structured_list.reject_non_terminal_row"

# Stable rule IDs for dependent-qualification reconciliation (extraction stage).
RULE_SUPPRESS_DEPENDENT_QUALIFICATION = (
    "extraction.suppress_dependent_qualification"
)

# Stable rule IDs for legal-effect classification and typed relationships.
RULE_DERIVE_LEGAL_EFFECT = "classification.derive_legal_effect"
RULE_INFER_EXCEPTION_TO = "relationship.infer_exception_to"
RULE_INFER_TRIGGERED_BY = "relationship.infer_triggered_by"
RULE_PREFER_GROUP_TARGET = "relationship.prefer_group_target"
RULE_INFERENCE_UNRESOLVED = "relationship.inference_unresolved"

# Stable rule IDs for legal-rule grouping and effective-law typed context.
RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP = "grouping.create_shared_fragment_rule_group"
RULE_ATTACH_APPLICABLE_EXCEPTION = "effective_law.attach_applicable_exception"
RULE_ATTACH_EXCEPTION_TARGET = "effective_law.attach_exception_target"
RULE_ATTACH_TRIGGER_CONDITION = "effective_law.attach_trigger_condition"
RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR = (
    "effective_law.prefer_typed_context_over_generic_locator"
)

# Provenance / source-effect explainability (20-BR9).
RULE_CLASSIFY_MANIFESTATION = "provenance.classify_manifestation"
RULE_PRESERVE_AS_OF_UNKNOWN = "provenance.preserve_as_of_unknown"
RULE_PARSE_AUTHORITY_ANNOTATION = "source_effect.parse_authority_annotation"
RULE_LINK_EXACT_FRAGMENT = "source_effect.link_exact_fragment"
RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR = "source_effect.inherit_from_structural_ancestor"
RULE_EXCLUDE_UNRELATED_FRAGMENT = "source_effect.exclude_unrelated_fragment"
RULE_CLASSIFY_OUTSTANDING_STATUS = "source_effect.classify_outstanding_status"
RULE_ASSESS_INDEPENDENT_CONSUMPTION = "source_effect.assess_independent_consumption"


@dataclass(frozen=True)
class HeuristicDefinition:
    """Immutable definition of a material Law Proposition Extractor heuristic rule."""

    rule_id: str
    version: str
    name: str
    plain_english_summary: str
    stage: DecisionStage
    method: HeuristicMethod
    input_kinds: tuple[str, ...]
    output_kinds: tuple[str, ...]
    trigger_summary: str
    precedence_summary: str
    failure_mode: str
    diagnostic_codes: tuple[str, ...]
    code_references: tuple[str, ...]
    test_references: tuple[str, ...]
    example_summary: str


def _build_registry() -> MappingProxyType[str, HeuristicDefinition]:
    definitions: list[HeuristicDefinition] = [
        HeuristicDefinition(
            rule_id=RULE_REQUIRED_LOCATOR,
            version="1",
            name="Required locator selection",
            plain_english_summary=(
                "Select a fragment for extraction when its locator is listed in "
                "the run's required locators configuration."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.CONFIGURATION,
            input_kinds=("source_fragment", "required_locator"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Extraction mode is frontier/local and the normalized fragment "
                "locator is present in configured required_locators."
            ),
            precedence_summary=(
                "Takes priority over focus-term matching, annex inclusion, and "
                "ordinary skip paths. Structural child preference does not "
                "override a required_locator parent."
            ),
            failure_mode=(
                "Missing required locators are recorded as warnings; the "
                "fragment is simply not selected via this rule."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.runner._select_fragment_for_extraction",
            ),
            test_references=(
                "tests/unit/test_selection_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a paragraph 1 is selected because the case requires "
                "article:49a:paragraph:1."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_FOCUS_TERM_MATCH,
            version="1",
            name="Focus-term selection",
            plain_english_summary=(
                "Select a fragment for extraction when its text strongly matches "
                "configured focus terms (at least two distinct term hits, or one "
                "multi-word term hit)."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("source_fragment", "focus_term"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Fragment is not already selected by required_locator or annex "
                "inclusion; focus-term strength check passes; selection mode is "
                "not required_only."
            ),
            precedence_summary=(
                "Applies after required_locator and annex inclusion. May later be "
                "suppressed by required-ancestor frontier preference."
            ),
            failure_mode=(
                "Weak or absent focus matches yield skipped_no_focus_match "
                "(not emitted as a DecisionExplanation)."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.runner._focus_match_strength",
                "law_proposition_extractor_pipeline.runner._select_fragment_for_extraction",
            ),
            test_references=(
                "tests/unit/test_selection_decision_explanations.py",
            ),
            example_summary=(
                "A subparagraph mentioning a multi-word focus species may be "
                "selected via focus_term_match before ancestor preference."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_SKIP_NON_OPERATIVE,
            version="1",
            name="Skip non-operative fragment",
            plain_english_summary=(
                "Exclude a fragment from extraction when its fragment type is "
                "non-operative (recital, heading, table, unknown, or document)."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("source_fragment",),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Frontier/local extraction reached the non-operative type check "
                "after required/focus/annex paths did not select the fragment."
            ),
            precedence_summary=(
                "Applies after required_locator, annex, required_only mode, empty "
                "focus config, focus match, and too-short checks fail to select."
            ),
            failure_mode="Fragment remains unselected with skip_reason non_operative.",
            diagnostic_codes=("non_operative",),
            code_references=(
                "law_proposition_extractor_pipeline.runner._is_non_operative_fragment",
                "law_proposition_extractor_pipeline.runner._select_fragment_for_extraction",
            ),
            test_references=(
                "tests/unit/test_selection_decision_explanations.py",
            ),
            example_summary="A recital fragment is excluded as non-operative.",
        ),
        HeuristicDefinition(
            rule_id=RULE_SKIP_TOO_SHORT,
            version="1",
            name="Skip too-short fragment",
            plain_english_summary=(
                "Exclude a fragment from extraction when its text length is below "
                "the configured minimum fragment character threshold."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.CONFIGURATION,
            input_kinds=("source_fragment", "min_fragment_chars"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Fragment was not selected by required/focus/annex paths and "
                "fragment_text_length < min_fragment_chars."
            ),
            precedence_summary=(
                "Checked before the non-operative type exclusion in the base "
                "selection function."
            ),
            failure_mode="Fragment remains unselected with skip_reason too_short.",
            diagnostic_codes=("too_short",),
            code_references=(
                "law_proposition_extractor_pipeline.runner._select_fragment_for_extraction",
            ),
            test_references=(
                "tests/unit/test_selection_decision_explanations.py",
            ),
            example_summary=(
                "A short structural label fragment below the minimum length is skipped."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_SKIP_REQUIRED_ONLY_MODE,
            version="1",
            name="Skip under required-only mode",
            plain_english_summary=(
                "Exclude a fragment that is not explicitly required when "
                "fragment_selection_mode is required_only."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.CONFIGURATION,
            input_kinds=("source_fragment", "fragment_selection_mode"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Mode is required_only and the fragment locator is not in "
                "required_locators (and annex inclusion does not apply)."
            ),
            precedence_summary=(
                "Applies immediately after required_locator and annex checks; "
                "blocks focus-term selection entirely."
            ),
            failure_mode=(
                "Fragment remains unselected with skip_reason "
                "skipped_not_required_in_required_only_mode."
            ),
            diagnostic_codes=("skipped_not_required_in_required_only_mode",),
            code_references=(
                "law_proposition_extractor_pipeline.runner._select_fragment_for_extraction",
            ),
            test_references=(
                "tests/unit/test_selection_decision_explanations.py",
            ),
            example_summary=(
                "In required_only mode, a focus-matching subparagraph is excluded "
                "because it was not listed as required."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PREFER_REQUIRED_CHILDREN,
            version="1",
            name="Prefer selected structural children",
            plain_english_summary=(
                "Suppress extraction of a selected parent when every substantive "
                "direct child is selected and those children collectively cover "
                "the parent's operative text."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("source_fragment", "structural_children"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Parent is selected (not via required_locator), has substantive "
                "direct children all selected, and children_cover_parent_operative_text "
                "returns true."
            ),
            precedence_summary=(
                "Runs after ordinary per-fragment selection; before required-ancestor "
                "frontier preference. Never overrides required_locator on the parent."
            ),
            failure_mode=(
                "When coverage is uncertain, the parent selection is left unchanged."
            ),
            diagnostic_codes=("covered_by_selected_children",),
            code_references=(
                "law_proposition_extractor_pipeline.structural_child_extraction_preference."
                "apply_structural_child_extraction_preference",
                "law_proposition_extractor_pipeline.structural_child_extraction_preference."
                "children_cover_parent_operative_text",
            ),
            test_references=(
                "tests/unit/test_structural_child_extraction_preference.py",
                "tests/unit/test_selection_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a is not extracted because paragraphs 1–3 cover its "
                "operative text."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PREFER_REQUIRED_ANCESTOR,
            version="1",
            name="Prefer required ancestor over focus descendant",
            plain_english_summary=(
                "Suppress a focus-selected descendant when an explicitly required "
                "selected ancestor already covers its operative text and "
                "structured-list terminals."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("source_fragment", "required_ancestor"),
            output_kinds=("selection_decision",),
            trigger_summary=(
                "Descendant selected via focus_term_match; nearest required_locator "
                "ancestor is selected; establish_ancestor_coverage succeeds."
            ),
            precedence_summary=(
                "Runs after structural child preference. Explicitly required "
                "descendants are never suppressed solely because an ancestor is "
                "also required."
            ),
            failure_mode=(
                "When coverage cannot be established safely, the descendant stays "
                "selected (or unresolved-overlap diagnostics may apply)."
            ),
            diagnostic_codes=(
                "covered_by_required_ancestor",
                "structured_list_ancestor_covers_descendant",
                "structural_descendant_text_contained",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.structural_extraction_frontier."
                "apply_required_ancestor_extraction_frontier",
                "law_proposition_extractor_pipeline.structural_extraction_frontier."
                "establish_ancestor_coverage",
            ),
            test_references=(
                "tests/unit/test_structural_extraction_frontier.py",
                "tests/unit/test_selection_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a paragraph 2(a) is not separately extracted because "
                "required paragraph 2 covers its structured-list terminals."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_STRUCTURAL_OVERLAP_UNRESOLVED,
            version="1",
            name="Unresolved selected structural overlap",
            plain_english_summary=(
                "Record a non-blocking diagnostic when both a required ancestor "
                "and a required nested descendant remain selected and text is "
                "nested, so neither can safely be suppressed."
            ),
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("source_fragment", "required_ancestor"),
            output_kinds=("selection_diagnostic",),
            trigger_summary=(
                "Both ancestor and descendant are selected via required_locator "
                "and descendant text is contained in the ancestor."
            ),
            precedence_summary=(
                "Does not change selection outcomes; appends "
                "selected_structural_overlap_unresolved to diagnostics."
            ),
            failure_mode="Diagnostic only; both fragments remain selected.",
            diagnostic_codes=("selected_structural_overlap_unresolved",),
            code_references=(
                "law_proposition_extractor_pipeline.structural_extraction_frontier."
                "apply_required_ancestor_extraction_frontier",
            ),
            test_references=(
                "tests/unit/test_structural_extraction_frontier.py",
                "tests/unit/test_selection_decision_explanations.py",
            ),
            example_summary=(
                "A required paragraph and a required nested subparagraph both "
                "stay selected with an unresolved-overlap diagnostic."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_COMPOSE_TERMINAL_LEAF,
            version="1",
            name="Compose structured-list terminal leaf",
            plain_english_summary=(
                "Compose the operative rule represented by a terminal "
                "structured-list path by combining the governing stem, any "
                "intermediate branch context, and the terminal leaf; attach "
                "canonical structured-list metadata and retain the composed "
                "candidate as a proposition."
            ),
            stage=DecisionStage.EXTRACTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "extraction_candidate",
                "structured_list_draft",
                "source_component",
            ),
            output_kinds=("proposition_candidate", "decision_explanation"),
            trigger_summary=(
                "A frontier extraction row is associated with a deterministic "
                "terminal structured-list draft, or a missing terminal is filled "
                "from that draft during merge_structured_leaf_rows."
            ),
            precedence_summary=(
                "Runs after LLM/heuristic row merge for a fragment and before "
                "opaque proposition IDs are assigned. Duplicate reconciliation "
                "for the same path may suppress other candidates first."
            ),
            failure_mode=(
                "If a terminal draft remains uncovered after merge, "
                "structured_list_terminal_uncovered is recorded; composition "
                "explanations are emitted only for retained terminals."
            ),
            diagnostic_codes=("structured_list_terminal_uncovered",),
            code_references=(
                "law_proposition_extractor_pipeline.structured_list_decomposition.merge_structured_leaf_rows",
                "law_proposition_extractor_pipeline.structured_list_decomposition._compose_effect",
                "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
                "build_structured_list_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_structured_list_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a path 2-a-ii is retained by combining the "
                "paragraph-2 stem, branch (a), and terminal point (ii)."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_SUPPRESS_DUPLICATE_TERMINAL,
            version="1",
            name="Suppress duplicate structured-list terminal",
            plain_english_summary=(
                "Identify multiple candidates that clearly express the same "
                "terminal legal claim for one structured-list path; choose one "
                "deterministic winner and suppress losing candidates."
            ),
            stage=DecisionStage.EXTRACTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("extraction_candidate", "structured_list_draft"),
            output_kinds=("suppressed_candidate", "decision_explanation"),
            trigger_summary=(
                "Two or more path-aligned candidates pass "
                "are_clear_structured_list_duplicates (path alone is not enough)."
            ),
            precedence_summary=(
                "Within a clear-duplicate group, "
                "select_structured_list_duplicate_winner chooses the retained "
                "row; suppressed candidates never become propositions."
            ),
            failure_mode=(
                "When safe duplication cannot be established, candidates are "
                "preserved under structured_list.preserve_distinct_terminal_claims "
                "instead of being suppressed."
            ),
            diagnostic_codes=("structured_list_terminal_duplicate_suppressed",),
            code_references=(
                "law_proposition_extractor_pipeline.structured_list_decomposition."
                "reconcile_structured_list_path_candidates",
                "law_proposition_extractor_pipeline.structured_list_decomposition."
                "select_structured_list_duplicate_winner",
                "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
                "build_structured_list_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_structured_list_terminal_dedupe.py",
                "tests/unit/test_structured_list_decision_explanations.py",
            ),
            example_summary=(
                "Two Article 49a 2-a-i paraphrases collapse to the candidate "
                "with the canonical :list:2-a-i locator."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS,
            version="1",
            name="Preserve distinct same-path terminal claims",
            plain_english_summary=(
                "Preserve multiple candidates that share one structured-list "
                "path when they are not safely established as duplicates; emit "
                "the existing focused diagnostic for review."
            ),
            stage=DecisionStage.EXTRACTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("extraction_candidate", "structured_list_draft"),
            output_kinds=("proposition_candidate", "decision_explanation"),
            trigger_summary=(
                "After pairwise duplicate grouping, more than one retained "
                "candidate remains for the same terminal path."
            ),
            precedence_summary=(
                "Applies only when are_clear_structured_list_duplicates does not "
                "collapse the candidates; does not assert authoritative legal "
                "distinctness."
            ),
            failure_mode=(
                "Diagnostic structured_list_path_multiple_distinct_propositions "
                "is retained; both candidates proceed for review."
            ),
            diagnostic_codes=("structured_list_path_multiple_distinct_propositions",),
            code_references=(
                "law_proposition_extractor_pipeline.structured_list_decomposition."
                "reconcile_structured_list_path_candidates",
                "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
                "build_structured_list_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_structured_list_terminal_dedupe.py",
                "tests/unit/test_structured_list_decision_explanations.py",
            ),
            example_summary=(
                "Two different operative claims on one path are both retained "
                "with a multiple-distinct diagnostic."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_REJECT_NON_TERMINAL_ROW,
            version="1",
            name="Reject stem- or branch-only structured-list row",
            plain_english_summary=(
                "Prevent a governing stem or intermediate branch from surviving "
                "as a standalone proposition where production logic treats it as "
                "non-terminal and represented through terminal compositions."
            ),
            stage=DecisionStage.EXTRACTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("extraction_candidate", "structured_list_draft"),
            output_kinds=("suppressed_candidate", "decision_explanation"),
            trigger_summary=(
                "An existing extraction row matches "
                "_is_stem_or_branch_only_row during merge_structured_leaf_rows "
                "(stem text without leaf distinctive text, or branch text "
                "without its roman leaf)."
            ),
            precedence_summary=(
                "Runs while associating frontier rows to terminal drafts; "
                "rejected rows are dropped before path bucketing. Explanations "
                "are emitted only for actual considered candidates, not for "
                "every XML branch that never became a candidate."
            ),
            failure_mode=(
                "Rows with a genuine independent operative claim (including "
                "leaf text) are not rejected by this rule."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.structured_list_decomposition."
                "_is_stem_or_branch_only_row",
                "law_proposition_extractor_pipeline.structured_list_decomposition.merge_structured_leaf_rows",
                "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
                "build_structured_list_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_structured_list_decision_explanations.py",
                "tests/unit/test_structured_list_decomposition.py",
            ),
            example_summary=(
                "A branch-(a)-only paraphrase is not retained; its context is "
                "incorporated into terminals 2-a-i and 2-a-ii."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_SUPPRESS_DEPENDENT_QUALIFICATION,
            version="1",
            name="Suppress dependent measurement qualification",
            plain_english_summary=(
                "Suppress a candidate that only describes how a threshold or "
                "distance condition in a governing operative proposition is "
                "measured, when the candidate has no independent legal effect "
                "and its measurement content is preserved on the retained row."
            ),
            stage=DecisionStage.EXTRACTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("extraction_candidate", "source_fragment"),
            output_kinds=("suppressed_candidate", "decision_explanation"),
            trigger_summary=(
                "A same-source, same-snapshot, same-fragment candidate states "
                "only a measurement methodology for a threshold already "
                "carried by a governing operative proposition; evidence is "
                "contained, overlapping, or linked under the same fragment; "
                "and preservation of the measurement basis succeeds."
            ),
            precedence_summary=(
                "Runs after structured-list terminal reconciliation and before "
                "proposition construction. Does not suppress exceptions, "
                "powers, recordkeeping duties, independent measurement "
                "obligations, cross-fragment/cross-snapshot rows, or ambiguous "
                "candidates."
            ),
            failure_mode=(
                "When independence, evidence linkage, unique governor, or "
                "content preservation cannot be established conservatively, "
                "the candidate is retained unchanged."
            ),
            diagnostic_codes=("dependent_qualification_measurement_suppressed",),
            code_references=(
                "law_proposition_extractor_pipeline.dependent_qualification."
                "reconcile_dependent_qualification_rows",
                "law_proposition_extractor_pipeline.heuristics.dependent_qualification_explanations."
                "build_dependent_qualification_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_dependent_qualification.py",
                "tests/unit/test_uk_regulation_12_measurement_replay.py",
            ),
            example_summary=(
                "UK regulation 12(2) 'The distance is measured from the edge "
                "of the surface water' is suppressed into the regulation 12 "
                "spreading prohibition, with the measurement basis preserved "
                "as a condition on the retained proposition."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_DERIVE_LEGAL_EFFECT,
            version="1",
            name="Derive legal-effect type",
            plain_english_summary=(
                "Assign legal_effect_type for a retained proposition using "
                "deterministic precedence: explicit priority cues, boilerplate, "
                "definition structure, substantive textual modals, extracted "
                "provision_type (non-cross-reference), cross-reference-only "
                "cues, then deferred provision_type cross_reference, else unknown."
            ),
            stage=DecisionStage.CLASSIFICATION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "proposition",
                "proposition_text",
                "extracted_provision_type",
                "structured_list_path",
            ),
            output_kinds=("legal_effect_type", "decision_explanation"),
            trigger_summary=(
                "Post-extraction classification runs for every retained "
                "proposition after frontier/local extraction."
            ),
            precedence_summary=(
                "explicit_priority → boilerplate → definition → substantive_text "
                "→ extracted_provision_type (except cross_reference) → "
                "cross_reference_text → deferred provision_type cross_reference "
                "→ fallback_unknown. Extracted provision_type may be an input "
                "even when a higher textual branch wins."
            ),
            failure_mode=(
                "When no textual or provision_type signal matches, "
                "legal_effect_type=unknown with winning_basis=fallback_unknown."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_domain.proposition_classification.derive_legal_effect_with_basis",
                "law_proposition_extractor_domain.proposition_classification.apply_post_extraction_classification",
                "law_proposition_extractor_pipeline.heuristics.classification_explanations."
                "build_classification_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_classification_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a E2 (path 2-a-ii): priority cue 'shall not apply' "
                "wins as explicit_exception_cue → derogation, even when the "
                "model proposed provision_type=exception."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_INFER_EXCEPTION_TO,
            version="1",
            name="Infer exception_to relationship",
            plain_english_summary=(
                "When a derogation/exception proposition contains a supported "
                "exception cue, bind the reference inside that cue span and "
                "infer an exception_to relationship to the safely resolved "
                "target. References outside the cue-target association remain "
                "ordinary contextual references."
            ),
            stage=DecisionStage.RELATIONSHIP,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "proposition",
                "exception_cue",
                "cue_bound_reference",
                "resolved_locator",
            ),
            output_kinds=("legal_rule_relationship", "decision_explanation"),
            trigger_summary=(
                "Source proposition is a derogation (or provision_type=exception) "
                "and text matches a supported exception cue pattern with a "
                "capturable reference."
            ),
            precedence_summary=(
                "Only the cue-bound reference becomes the typed target. Other "
                "explicit cross-references on the same proposition are not "
                "promoted to exception_to."
            ),
            failure_mode=(
                "Unparseable cue references, non-unique association, or "
                "ambiguous/missing targets emit diagnostics without a "
                "relationship."
            ),
            diagnostic_codes=(
                "typed_relationship_cue_reference_parse_failed",
                "typed_relationship_reference_not_uniquely_associated",
                "typed_relationship_cue_reference_no_matching_target",
                "typed_relationship_target_ambiguous",
                "typed_relationship_target_group_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.legal_rule_relationships.build_legal_rule_relationships",
                "law_proposition_extractor_pipeline.legal_rule_relationships._try_build_for_cue",
                "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
                "build_relationship_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_relationship_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a E3: 'Paragraph 1 shall not apply' → exception_to "
                "article:49a:paragraph:1; Article 14 stays ordinary."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_INFER_TRIGGERED_BY,
            version="2",
            name="Infer triggered_by relationship",
            plain_english_summary=(
                "When a proposition contains supported trigger phrasing such as "
                "'in the cases referred to in …' or 'where the cases referred to "
                "in … apply', bind the cue-span reference and infer a triggered_by "
                "relationship to the safely resolved target."
            ),
            stage=DecisionStage.RELATIONSHIP,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "proposition",
                "trigger_cue",
                "cue_bound_reference",
                "resolved_locator",
            ),
            output_kinds=("legal_rule_relationship", "decision_explanation"),
            trigger_summary=(
                "Proposition text matches a supported trigger cue pattern with "
                "a capturable reference."
            ),
            precedence_summary=(
                "Trigger cues are independent of derogation gating; association "
                "and targeting follow the same conservative resolution path as "
                "exception_to."
            ),
            failure_mode=(
                "Failed cue association or unsafe targeting emits a diagnostic "
                "without claiming a relationship. Near-miss 'referred to in' "
                "language without a supported cue frame is recorded as "
                "no_supported_trigger_cue."
            ),
            diagnostic_codes=(
                "typed_relationship_no_supported_trigger_cue",
                "typed_relationship_cue_found_but_no_bound_reference",
                "typed_relationship_cue_reference_parse_failed",
                "typed_relationship_reference_not_uniquely_associated",
                "typed_relationship_cue_reference_no_matching_target",
                "typed_relationship_target_ambiguous",
                "typed_relationship_target_group_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.legal_rule_relationships.build_legal_rule_relationships",
                "law_proposition_extractor_pipeline.legal_rule_relationships._try_build_for_cue",
                "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
                "build_relationship_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_relationship_decision_explanations.py",
                "tests/unit/test_legal_rule_relationships_trigger_cues.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a P3: 'in the cases referred to in Article 49a(2)' "
                "or 'where the cases referred to in paragraph 2 apply' "
                "→ triggered_by article:49a:paragraph:2."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PREFER_GROUP_TARGET,
            version="1",
            name="Prefer LegalRuleGroup as relationship target",
            plain_english_summary=(
                "Where the resolved provision has one persisted LegalRuleGroup "
                "in the same source/snapshot scope, Law Proposition Extractor targets the group so "
                "downstream context can be inherited by all of its member "
                "propositions. Falls back to a unique retained proposition; "
                "never fans out to multiple targets."
            ),
            stage=DecisionStage.RELATIONSHIP,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "resolved_locator",
                "legal_rule_group",
                "source_snapshot_scope",
            ),
            output_kinds=("legal_rule_relationship", "decision_explanation"),
            trigger_summary=(
                "A typed relationship cue has been safely associated and "
                "resolved to a unique target locator."
            ),
            precedence_summary=(
                "1) unique source/snapshot-scoped LegalRuleGroup for the "
                "target fragment; 2) otherwise unique retained proposition; "
                "3) otherwise no relationship plus diagnostic."
            ),
            failure_mode=(
                "Ambiguous groups or multi-proposition fragments without a "
                "group emit typed_relationship_target_ambiguous / "
                "typed_relationship_target_group_missing."
            ),
            diagnostic_codes=(
                "typed_relationship_target_ambiguous",
                "typed_relationship_target_group_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.legal_rule_relationships._select_target",
                "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
                "build_relationship_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_relationship_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a exception_to targets the paragraph-1 group "
                "(P1+P2), not either paragraph-1 proposition individually."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_INFERENCE_UNRESOLVED,
            version="1",
            name="Typed relationship inference unresolved",
            plain_english_summary=(
                "Record a material attempted typed-relationship inference that "
                "could not safely complete. Does not claim a relationship exists."
            ),
            stage=DecisionStage.RELATIONSHIP,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "proposition",
                "exception_or_trigger_cue",
                "diagnostic",
            ),
            output_kinds=("decision_explanation",),
            trigger_summary=(
                "A supported exception or trigger cue was detected but cue "
                "association, locator resolution, or target selection failed "
                "conservatively; or near-miss 'referred to in' trigger-like "
                "language lacked a supported cue frame."
            ),
            precedence_summary=(
                "Emitted only for material attempted typed inferences; "
                "propositions without exception/trigger cues or near-miss "
                "trigger language produce no explanation."
            ),
            failure_mode=(
                "This rule is the failure explanation itself; outcome names "
                "the diagnostic code."
            ),
            diagnostic_codes=(
                "typed_relationship_no_supported_trigger_cue",
                "typed_relationship_cue_found_but_no_bound_reference",
                "typed_relationship_cue_reference_parse_failed",
                "typed_relationship_reference_not_uniquely_associated",
                "typed_relationship_cue_reference_no_matching_target",
                "typed_relationship_target_ambiguous",
                "typed_relationship_target_group_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.legal_rule_relationships._try_build_for_cue",
                "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
                "build_relationship_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_relationship_decision_explanations.py",
            ),
            example_summary=(
                "Ambiguous cue association emits reference_not_uniquely_associated "
                "without creating an exception_to edge."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP,
            version="1",
            name="Create shared-fragment LegalRuleGroup",
            plain_english_summary=(
                "Law Proposition Extractor groups two or more retained propositions that share the "
                "same source_record_id, source_snapshot_id, and source_fragment_id "
                "when that fragment has a reliable canonical locator. Grouping is "
                "structural (shared source fragment), not textual similarity, "
                "shared topic, shared legal-effect classification, or model "
                "judgment. Members are ordered by deterministic source order. "
                "Single-member fragments, unreliable locators, mixed "
                "source/snapshot/fragment buckets, article-level aggregates, and "
                "descendant roll-ups do not form groups."
            ),
            stage=DecisionStage.GROUPING,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "retained_proposition",
                "source_fragment",
                "source_snapshot_scope",
            ),
            output_kinds=("legal_rule_group", "decision_explanation"),
            trigger_summary=(
                "At least two retained propositions share one reliable source "
                "fragment within the same source record and snapshot."
            ),
            precedence_summary=(
                "Direct shared-fragment membership only; minimum member count is "
                "2; canonical locator must be reliable; members sorted by "
                "source_order (with deterministic fallback)."
            ),
            failure_mode=(
                "Fewer than two members, missing source identities, unreliable "
                "locator, or source/snapshot mismatch → no group."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.legal_rule_groups.build_legal_rule_groups",
                "law_proposition_extractor_pipeline.heuristics.grouping_explanations."
                "build_grouping_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_grouping_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a paragraph 1 yields one group for P1+P2; paragraph 3 "
                "alone does not form a group."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_ATTACH_APPLICABLE_EXCEPTION,
            version="1",
            name="Attach applicable exception context",
            plain_english_summary=(
                "When an exception_to relationship targets a LegalRuleGroup (or "
                "proposition), the effective-law composer attaches the exception "
                "proposition as applicable_exception on each expanded target "
                "member. This is a presentation/context projection of the "
                "existing typed relationship, not a new inferred edge."
            ),
            stage=DecisionStage.EFFECTIVE_LAW,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "legal_rule_relationship",
                "legal_rule_group",
                "effective_law_statement",
            ),
            output_kinds=("required_context", "decision_explanation"),
            trigger_summary=(
                "A persisted exception_to relationship expands to one or more "
                "retained target propositions."
            ),
            precedence_summary=(
                "Group targets expand one level to members with "
                "inherited_via_group=true; direct proposition targets set "
                "inherited_via_group=false."
            ),
            failure_mode=(
                "Missing source/target/group members emit composition diagnostics "
                "without attaching context."
            ),
            diagnostic_codes=(
                "effective_law_relationship_source_missing",
                "effective_law_relationship_target_missing",
                "effective_law_relationship_group_missing",
                "effective_law_relationship_group_member_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.effective_law._collect_typed_required_contexts",
                "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
                "build_effective_law_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_effective_law_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a: E1/E2/E3 become applicable_exception on P1 and P2 "
                "via the paragraph-1 group."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_ATTACH_EXCEPTION_TARGET,
            version="1",
            name="Attach exception-target context",
            plain_english_summary=(
                "For each exception_to expansion, attach the displaced rule "
                "propositions as exception_target on the exception proposition. "
                "Members come from the targeted group (or the direct proposition "
                "target). This projects the existing exception_to relationship "
                "into reviewer-facing context; it is not a separate inferred "
                "relationship."
            ),
            stage=DecisionStage.EFFECTIVE_LAW,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "legal_rule_relationship",
                "legal_rule_group",
                "effective_law_statement",
            ),
            output_kinds=("required_context", "decision_explanation"),
            trigger_summary=(
                "A persisted exception_to relationship expands to retained "
                "target propositions."
            ),
            precedence_summary=(
                "Emitted on the relationship source for each expanded target "
                "member; pairs with applicable_exception on those members."
            ),
            failure_mode=(
                "Missing endpoints omit the context attachment and may record "
                "composition diagnostics."
            ),
            diagnostic_codes=(
                "effective_law_relationship_target_missing",
                "effective_law_relationship_group_member_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.effective_law._collect_typed_required_contexts",
                "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
                "build_effective_law_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_effective_law_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a: P1 and P2 appear as exception_target on E1, E2, "
                "and E3."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_ATTACH_TRIGGER_CONDITION,
            version="1",
            name="Attach trigger-condition context",
            plain_english_summary=(
                "When a triggered_by relationship targets a LegalRuleGroup (or "
                "proposition), attach each expanded target member as "
                "trigger_condition on the relationship source only. Current "
                "semantics are source-only: no reverse trigger context is "
                "projected onto the trigger propositions."
            ),
            stage=DecisionStage.EFFECTIVE_LAW,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "legal_rule_relationship",
                "legal_rule_group",
                "effective_law_statement",
            ),
            output_kinds=("required_context", "decision_explanation"),
            trigger_summary=(
                "A persisted triggered_by relationship expands to retained "
                "target propositions."
            ),
            precedence_summary=(
                "Projection is source-only (expansion_direction=source_only); "
                "group members inherit with inherited_via_group=true."
            ),
            failure_mode=(
                "Missing endpoints omit trigger-condition attachment."
            ),
            diagnostic_codes=(
                "effective_law_relationship_target_missing",
                "effective_law_relationship_group_member_missing",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.effective_law._collect_typed_required_contexts",
                "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
                "build_effective_law_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_effective_law_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a: E1/E2/E3 become trigger_condition on P3; P3 is not "
                "projected backwards onto E1/E2/E3."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR,
            version="1",
            name="Prefer typed context over generic locator",
            plain_english_summary=(
                "When a generic locator required-context entry resolves only to "
                "propositions already represented by typed legal-relationship "
                "context on the same statement, omit that generic duplicate. "
                "Typed context has priority only where the generic entry "
                "represents the same source/target legal connection. Unrelated "
                "ordinary references (for example Article 14 beside a "
                "paragraph-1 exception) remain."
            ),
            stage=DecisionStage.EFFECTIVE_LAW,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "required_context",
                "typed_required_context",
                "effective_law_statement",
            ),
            output_kinds=("required_context", "decision_explanation"),
            trigger_summary=(
                "A generic non-external locator context entry's proposition_ids "
                "are fully covered by typed applicable_exception, "
                "exception_target, or trigger_condition context on the same "
                "statement."
            ),
            precedence_summary=(
                "Suppress only fully covered generic duplicates; partial "
                "coverage trims matched ids; external references and uncovered "
                "ordinary locators are retained."
            ),
            failure_mode=(
                "No suppression when typed coverage is empty or the generic "
                "target propositions are not covered."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.effective_law._dedupe_locator_context_against_typed",
                "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
                "build_effective_law_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_effective_law_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a E3: paragraph-1 generic locator suppressed; "
                "Article 14 ordinary referenced_locator retained."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_CLASSIFY_MANIFESTATION,
            version="1",
            name="Classify source manifestation",
            plain_english_summary=(
                "Classify the consumed snapshot as original, revised, "
                "point_in_time, prospective, or unknown from authority "
                "metadata and URL evidence. Prefer explicit source metadata "
                "over resolved URL over requested URL. Conflicts yield "
                "unknown rather than a guessed type. Does not assert that "
                "Law Proposition Extractor applied amendments."
            ),
            stage=DecisionStage.PROVENANCE,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_snapshot",
                "requested_url",
                "resolved_url",
                "source_metadata",
            ),
            output_kinds=("manifestation_type", "decision_explanation"),
            trigger_summary=(
                "A SourceSnapshot is materialised from a legislation.gov.uk "
                "fetch with manifestation provenance resolution."
            ),
            precedence_summary=(
                "Source metadata wins when present; otherwise resolved URL; "
                "otherwise request URL (audit-only, type unknown unless "
                "resolved). Incompatible request/source evidence clears the "
                "resolved type to unknown."
            ),
            failure_mode=(
                "Insufficient or conflicting evidence yields manifestation "
                "type unknown with retained conflict diagnostics."
            ),
            diagnostic_codes=("manifestation_conflict",),
            code_references=(
                "law_proposition_extractor_pipeline.sources.legislation_manifestation."
                "resolve_manifestation_provenance",
                "law_proposition_extractor_pipeline.heuristics.provenance_explanations."
                "build_provenance_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a: DocumentStatus=revised → revised with "
                "basis=source_metadata; requested/resolved as-of remain null."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PRESERVE_AS_OF_UNKNOWN,
            version="1",
            name="Preserve legal as-of as not established",
            plain_english_summary=(
                "When the consumed request and source metadata do not "
                "establish a point-in-time legal as-of date, leave "
                "requested/resolved as-of unset. Retrieval time and source "
                "revision date remain separate operational/authority "
                "metadata and are not treated as legal as-of."
            ),
            stage=DecisionStage.PROVENANCE,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_snapshot",
                "manifestation_type",
                "retrieved_at",
                "source_revision_date",
            ),
            output_kinds=("resolved_as_of_date", "decision_explanation"),
            trigger_summary=(
                "Manifestation resolution completes without a point-in-time "
                "as-of date (including revised/original/prospective/unknown)."
            ),
            precedence_summary=(
                "Legal as-of is set only for point_in_time manifestations "
                "with an authority-resolved date; otherwise both as-of "
                "fields stay null."
            ),
            failure_mode=(
                "Does not invent an as-of date from retrieval or revision "
                "stamps."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.sources.legislation_manifestation."
                "resolve_manifestation_provenance",
                "law_proposition_extractor_pipeline.heuristics.provenance_explanations."
                "build_provenance_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a revised snapshot: retrieval and revision dates "
                "recorded; legal as-of not established."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_PARSE_AUTHORITY_ANNOTATION,
            version="1",
            name="Parse authority source-effect annotation",
            plain_english_summary=(
                "Retain a material authority-provided amendment/effect "
                "annotation from consumed CLML (commentary and change "
                "markers). Records category, label, affecting-instrument "
                "identifiers, and affected locator as reported by the "
                "source. Does not apply the amendment or verify correctness."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("clml_commentary", "change_marker", "source_snapshot"),
            output_kinds=("source_legal_effect", "decision_explanation"),
            trigger_summary=(
                "A retained SourceLegalEffect is parsed from authority "
                "commentary/change metadata in the consumed snapshot."
            ),
            precedence_summary=(
                "Change-element type hints prefer Substitution/Repeal/Omit/"
                "Addition; otherwise commentary text markers; bare Type=F "
                "footnotes without amendment content are ignored."
            ),
            failure_mode=(
                "Unresolved CommentaryRef produces diagnostics; ignored "
                "footnotes emit no false source-effect decisions."
            ),
            diagnostic_codes=("source_effect_reference_unresolved",),
            code_references=(
                "law_proposition_extractor_pipeline.sources.legislation_effects.parse_source_legal_effects",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a F2/F4/F5/F6 annotations retained with affecting "
                "instrument identifiers from Citation elements."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_LINK_EXACT_FRAGMENT,
            version="1",
            name="Link source effect to exact fragment",
            plain_english_summary=(
                "Mark a source-reported effect as relevant to a reviewer-"
                "facing statement when the effect is linked to the same "
                "source fragment or locator as the statement's proposition. "
                "Exact match only — does not inherit across structure."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_legal_effect",
                "source_legal_effect_link",
                "effective_law_statement",
            ),
            output_kinds=("source_effect_relevance", "decision_explanation"),
            trigger_summary=(
                "An effect link (or effect-level locator) exactly matches "
                "the receiving proposition's fragment or locator within the "
                "same source/snapshot."
            ),
            precedence_summary=(
                "Exact fragment/locator match takes priority over structural "
                "ancestor inheritance for the same effect."
            ),
            failure_mode=(
                "No exact-link relevance when fragment and locator differ; "
                "sibling paragraphs do not match."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.source_effect_relevance."
                "capture_source_effect_relevance_facts",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Paragraph-2 substitution annotation linked exactly to "
                "Article 49a paragraph 2 statements."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
            version="1",
            name="Inherit source effect from structural ancestor",
            plain_english_summary=(
                "Show an effect attached to a genuine structural ancestor "
                "(for example Article 49a) on propositions extracted from "
                "descendant paragraphs. Does not claim the effect modifies "
                "every descendant proposition identically."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_legal_effect",
                "source_fragment_hierarchy",
                "effective_law_statement",
            ),
            output_kinds=("source_effect_relevance", "decision_explanation"),
            trigger_summary=(
                "An effect is linked to an ancestor fragment/locator of the "
                "receiving proposition within the same source/snapshot, and "
                "no exact match exists for that effect."
            ),
            precedence_summary=(
                "Uses validated parent edges and locator-prefix ancestry; "
                "invalid sibling-article edges are not traversed."
            ),
            failure_mode=(
                "No inheritance across unrelated branches or invalid parent "
                "edges; cycles abort traversal."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.source_effect_relevance."
                "capture_source_effect_relevance_facts",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a-level F2 annotation shown on paragraph 1–3 "
                "statements via structural_ancestor relevance."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_EXCLUDE_UNRELATED_FRAGMENT,
            version="1",
            name="Exclude unrelated structural-branch effect",
            plain_english_summary=(
                "Exclude a same-snapshot effect linked to a different "
                "top-level provision that is not a structural ancestor of "
                "the receiving statement (for example Article 1 vs "
                "Article 49a). Focused exclusion for material "
                "false-positive risk — not a blanket negative for every "
                "irrelevant effect."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_legal_effect",
                "source_fragment_hierarchy",
                "effective_law_statement",
            ),
            output_kinds=("source_effect_relevance", "decision_explanation"),
            trigger_summary=(
                "A scoped effect is linked to a top-level provision locator "
                "whose root provision differs from the receiving "
                "statement's root provision and is not an ancestor."
            ),
            precedence_summary=(
                "Emitted only for top-level sibling/unrelated provision "
                "branches considered during relevance matching."
            ),
            failure_mode=(
                "Does not emit thousands of negatives for every non-matching "
                "effect; paragraph siblings are isolated by positive-match "
                "absence instead."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.source_effect_relevance."
                "capture_source_effect_relevance_facts",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 1 F1 effect excluded from Article 49a statements "
                "because Article 1 is not a structural ancestor."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_CLASSIFY_OUTSTANDING_STATUS,
            version="1",
            name="Classify outstanding-effects status",
            plain_english_summary=(
                "Derive snapshot/run outstanding-effects status only from "
                "authority metadata (UnappliedEffects). Distinguishes "
                "source_reports_present, source_reports_none, and "
                "source_status_unknown. Revised manifestation does not "
                "imply none."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=("unapplied_effects_metadata", "source_snapshot"),
            output_kinds=("outstanding_effects_status", "decision_explanation"),
            trigger_summary=(
                "Source legal-effects inventory records an aggregate "
                "outstanding_effects_status from consumed CLML."
            ),
            precedence_summary=(
                "Any snapshot reporting present wins at aggregate level; "
                "all-none yields none; otherwise unknown."
            ),
            failure_mode=(
                "Absence of UnappliedEffects metadata yields unknown — not "
                "none."
            ),
            diagnostic_codes=(),
            code_references=(
                "law_proposition_extractor_pipeline.sources.legislation_effects._outstanding_status",
                "law_proposition_extractor_pipeline.source_legal_effects."
                "build_source_legal_effects_artifact",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a fixture: UnappliedEffects present → "
                "source_reports_present."
            ),
        ),
        HeuristicDefinition(
            rule_id=RULE_ASSESS_INDEPENDENT_CONSUMPTION,
            version="1",
            name="Assess independent consumption of affecting instrument",
            plain_english_summary=(
                "Run-scoped identity match of an affecting instrument to "
                "independently consumed SourceRecord/SourceSnapshot rows "
                "(or register-only entries). Statuses: consumed_in_current_run, "
                "present_in_source_register_but_not_consumed, not_matched, "
                "not_assessed. Consumption does not prove the amendment was "
                "applied or verified."
            ),
            stage=DecisionStage.SOURCE_EFFECT,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(
                "source_legal_effect",
                "source_records",
                "source_snapshots",
                "source_register",
            ),
            output_kinds=(
                "independent_consumption_status",
                "decision_explanation",
            ),
            trigger_summary=(
                "Source legal-effects artifact reconciliation runs against "
                "the current run inventory."
            ),
            precedence_summary=(
                "Strong URI/identifier/CELEX/citation signals; ambiguous or "
                "conflicting matches yield not_matched; insufficient "
                "identity yields not_assessed."
            ),
            failure_mode=(
                "not_matched means no match in this run — not that the "
                "instrument does not exist. not_assessed means matching "
                "was not attempted with usable identity."
            ),
            diagnostic_codes=(
                "affecting_instrument_identifier_insufficient",
                "affecting_instrument_match_ambiguous",
                "affecting_instrument_identity_conflict",
            ),
            code_references=(
                "law_proposition_extractor_pipeline.affecting_instrument_consumption."
                "reconcile_source_legal_effects_artifact",
                "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
                "build_source_effect_decision_explanations",
            ),
            test_references=(
                "tests/unit/test_provenance_decision_explanations.py",
                "tests/unit/test_affecting_instrument_consumption.py",
                "tests/acceptance/test_article_49a_legal_structure.py",
            ),
            example_summary=(
                "Article 49a affecting UKSI identifiers: not_matched in the "
                "narrow EUR-only fixture run."
            ),
        ),
    ]

    by_id: dict[str, HeuristicDefinition] = {}
    for definition in definitions:
        if not definition.version or not str(definition.version).strip():
            raise ValueError(
                f"Heuristic {definition.rule_id!r} has an empty version."
            )
        if definition.rule_id in by_id:
            raise ValueError(
                f"Duplicate heuristic rule_id {definition.rule_id!r}."
            )
        by_id[definition.rule_id] = definition
    # Deterministic ordering: sorted by rule_id.
    ordered = {key: by_id[key] for key in sorted(by_id)}
    return MappingProxyType(ordered)


_REGISTRY: MappingProxyType[str, HeuristicDefinition] = _build_registry()


def get_heuristic(rule_id: str) -> HeuristicDefinition | None:
    """Return a registered heuristic, or None if unknown."""
    return _REGISTRY.get(str(rule_id))


def require_heuristic(rule_id: str) -> HeuristicDefinition:
    """Return a registered heuristic or raise KeyError with a clear message."""
    key = str(rule_id)
    definition = _REGISTRY.get(key)
    if definition is None:
        known = ", ".join(_REGISTRY.keys()) or "(none)"
        raise KeyError(
            f"Unknown heuristic rule_id {key!r}. Known rule_ids: {known}."
        )
    return definition


def list_heuristics() -> tuple[HeuristicDefinition, ...]:
    """Return all heuristics in deterministic rule_id order."""
    return tuple(_REGISTRY[key] for key in _REGISTRY)
