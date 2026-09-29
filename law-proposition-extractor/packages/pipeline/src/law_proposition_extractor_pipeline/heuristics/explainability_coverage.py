"""Explainability emission coverage for registered heuristics.

This module is the typed declaration connecting heuristic rule IDs to
DecisionExplanation emission sites. A rule may be registered without emitting
decisions; do not infer coverage from registry membership alone.
"""

from __future__ import annotations

from types import MappingProxyType

from .registry import (
    RULE_ASSESS_INDEPENDENT_CONSUMPTION,
    RULE_ATTACH_APPLICABLE_EXCEPTION,
    RULE_ATTACH_EXCEPTION_TARGET,
    RULE_ATTACH_TRIGGER_CONDITION,
    RULE_CLASSIFY_MANIFESTATION,
    RULE_CLASSIFY_OUTSTANDING_STATUS,
    RULE_COMPOSE_TERMINAL_LEAF,
    RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP,
    RULE_DERIVE_LEGAL_EFFECT,
    RULE_EXCLUDE_UNRELATED_FRAGMENT,
    RULE_FOCUS_TERM_MATCH,
    RULE_INFER_EXCEPTION_TO,
    RULE_INFER_TRIGGERED_BY,
    RULE_INFERENCE_UNRESOLVED,
    RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
    RULE_LINK_EXACT_FRAGMENT,
    RULE_PARSE_AUTHORITY_ANNOTATION,
    RULE_PREFER_GROUP_TARGET,
    RULE_PREFER_REQUIRED_ANCESTOR,
    RULE_PREFER_REQUIRED_CHILDREN,
    RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR,
    RULE_PRESERVE_AS_OF_UNKNOWN,
    RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS,
    RULE_REJECT_NON_TERMINAL_ROW,
    RULE_REQUIRED_LOCATOR,
    RULE_SKIP_NON_OPERATIVE,
    RULE_SKIP_REQUIRED_ONLY_MODE,
    RULE_SKIP_TOO_SHORT,
    RULE_STRUCTURAL_OVERLAP_UNRESOLVED,
    RULE_SUPPRESS_DEPENDENT_QUALIFICATION,
    RULE_SUPPRESS_DUPLICATE_TERMINAL,
    list_heuristics,
)

# rule_id → emission site module.symbol (builder or attach helper).
_EMISSION_SITES: dict[str, str] = {
    RULE_REQUIRED_LOCATOR: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_FOCUS_TERM_MATCH: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_SKIP_NON_OPERATIVE: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_SKIP_TOO_SHORT: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_SKIP_REQUIRED_ONLY_MODE: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_PREFER_REQUIRED_CHILDREN: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_PREFER_REQUIRED_ANCESTOR: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_STRUCTURAL_OVERLAP_UNRESOLVED: (
        "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
    ),
    RULE_COMPOSE_TERMINAL_LEAF: (
        "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
        "build_structured_list_decision_explanations"
    ),
    RULE_SUPPRESS_DUPLICATE_TERMINAL: (
        "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
        "build_structured_list_decision_explanations"
    ),
    RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS: (
        "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
        "build_structured_list_decision_explanations"
    ),
    RULE_REJECT_NON_TERMINAL_ROW: (
        "law_proposition_extractor_pipeline.heuristics.structured_list_explanations."
        "build_structured_list_decision_explanations"
    ),
    RULE_SUPPRESS_DEPENDENT_QUALIFICATION: (
        "law_proposition_extractor_pipeline.heuristics.dependent_qualification_explanations."
        "build_dependent_qualification_decision_explanations"
    ),
    RULE_DERIVE_LEGAL_EFFECT: (
        "law_proposition_extractor_pipeline.heuristics.classification_explanations."
        "build_classification_decision_explanations"
    ),
    RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP: (
        "law_proposition_extractor_pipeline.heuristics.grouping_explanations.build_grouping_decision_explanations"
    ),
    RULE_INFER_EXCEPTION_TO: (
        "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
        "build_relationship_decision_explanations"
    ),
    RULE_INFER_TRIGGERED_BY: (
        "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
        "build_relationship_decision_explanations"
    ),
    RULE_PREFER_GROUP_TARGET: (
        "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
        "build_relationship_decision_explanations"
    ),
    RULE_INFERENCE_UNRESOLVED: (
        "law_proposition_extractor_pipeline.heuristics.relationship_explanations."
        "build_relationship_decision_explanations"
    ),
    RULE_ATTACH_APPLICABLE_EXCEPTION: (
        "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
        "build_effective_law_decision_explanations"
    ),
    RULE_ATTACH_EXCEPTION_TARGET: (
        "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
        "build_effective_law_decision_explanations"
    ),
    RULE_ATTACH_TRIGGER_CONDITION: (
        "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
        "build_effective_law_decision_explanations"
    ),
    RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR: (
        "law_proposition_extractor_pipeline.heuristics.effective_law_explanations."
        "build_effective_law_decision_explanations"
    ),
    RULE_CLASSIFY_MANIFESTATION: (
        "law_proposition_extractor_pipeline.heuristics.provenance_explanations."
        "build_provenance_decision_explanations"
    ),
    RULE_PRESERVE_AS_OF_UNKNOWN: (
        "law_proposition_extractor_pipeline.heuristics.provenance_explanations."
        "build_provenance_decision_explanations"
    ),
    RULE_PARSE_AUTHORITY_ANNOTATION: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
    RULE_LINK_EXACT_FRAGMENT: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
    RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
    RULE_EXCLUDE_UNRELATED_FRAGMENT: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
    RULE_CLASSIFY_OUTSTANDING_STATUS: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
    RULE_ASSESS_INDEPENDENT_CONSUMPTION: (
        "law_proposition_extractor_pipeline.heuristics.source_effect_explanations."
        "build_source_effect_decision_explanations"
    ),
}

RULES_EMITTING_DECISION_EXPLANATIONS: frozenset[str] = frozenset(_EMISSION_SITES)
EMISSION_SITES: MappingProxyType[str, str] = MappingProxyType(_EMISSION_SITES)


def rules_emitting_explanations() -> tuple[str, ...]:
    """Registered rule IDs that have DecisionExplanation emission sites."""
    return tuple(sorted(RULES_EMITTING_DECISION_EXPLANATIONS))


def rules_not_yet_emitting_explanations() -> tuple[str, ...]:
    """Registered rule IDs without a declared emission site."""
    registered = {h.rule_id for h in list_heuristics()}
    missing = registered - RULES_EMITTING_DECISION_EXPLANATIONS
    return tuple(sorted(missing))


def emits_decision_explanation(rule_id: str) -> bool:
    """Return True when the rule has a declared DecisionExplanation emitter."""
    return str(rule_id) in RULES_EMITTING_DECISION_EXPLANATIONS
