"""Typed Law Proposition Extractor heuristic registry and decision explainability helpers."""

from .classification_explanations import (
    build_classification_decision_explanations,
    classification_facts_from_propositions,
)
from .dependent_qualification_explanations import (
    bind_dependent_qualification_decision_facts,
    build_dependent_qualification_decision_explanations,
)
from .effective_law_explanations import (
    bind_effective_law_decision_facts,
    build_effective_law_decision_explanations,
)
from .explainability_coverage import (
    EMISSION_SITES,
    RULES_EMITTING_DECISION_EXPLANATIONS,
    emits_decision_explanation,
    rules_emitting_explanations,
    rules_not_yet_emitting_explanations,
)
from .grouping_explanations import build_grouping_decision_explanations
from .registry import (
    REGISTRY_VERSION,
    HeuristicDefinition,
    get_heuristic,
    list_heuristics,
    require_heuristic,
)
from .provenance_attach import attach_provenance_and_source_effect_explanations
from .provenance_explanations import (
    build_provenance_decision_explanations,
    collect_manifestation_decision_facts,
)
from .relationship_explanations import (
    build_relationship_decision_explanations,
    relationship_candidate_id,
)
from .selection_explanations import (
    attach_decision_explanations,
    build_decision_explanations_artifact,
    build_selection_decision_explanations,
    decision_explanation_id,
)
from .source_effect_explanations import (
    build_source_effect_decision_explanations,
    collect_consumption_decision_facts,
    collect_parse_and_outstanding_facts,
)
from .structured_list_explanations import (
    bind_structured_list_decision_facts,
    build_structured_list_decision_explanations,
    merge_decision_explanation_lists,
)

__all__ = [
    "EMISSION_SITES",
    "REGISTRY_VERSION",
    "RULES_EMITTING_DECISION_EXPLANATIONS",
    "HeuristicDefinition",
    "attach_decision_explanations",
    "attach_provenance_and_source_effect_explanations",
    "bind_dependent_qualification_decision_facts",
    "bind_effective_law_decision_facts",
    "bind_structured_list_decision_facts",
    "build_classification_decision_explanations",
    "build_decision_explanations_artifact",
    "build_dependent_qualification_decision_explanations",
    "build_effective_law_decision_explanations",
    "build_grouping_decision_explanations",
    "build_provenance_decision_explanations",
    "build_relationship_decision_explanations",
    "build_selection_decision_explanations",
    "build_source_effect_decision_explanations",
    "build_structured_list_decision_explanations",
    "classification_facts_from_propositions",
    "collect_consumption_decision_facts",
    "collect_manifestation_decision_facts",
    "collect_parse_and_outstanding_facts",
    "decision_explanation_id",
    "emits_decision_explanation",
    "get_heuristic",
    "list_heuristics",
    "merge_decision_explanation_lists",
    "relationship_candidate_id",
    "require_heuristic",
    "rules_emitting_explanations",
    "rules_not_yet_emitting_explanations",
]
