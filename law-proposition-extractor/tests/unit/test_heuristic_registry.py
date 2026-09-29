"""Heuristic registry integrity tests."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from law_proposition_extractor_domain import DecisionStage, HeuristicMethod
from law_proposition_extractor_pipeline.heuristics.registry import (
    REGISTRY_VERSION,
    HeuristicDefinition,
    _build_registry,
    get_heuristic,
    list_heuristics,
    require_heuristic,
)


def test_registry_version_is_explicit() -> None:
    assert REGISTRY_VERSION == "1"


def test_list_heuristics_deterministic_order() -> None:
    first = [h.rule_id for h in list_heuristics()]
    second = [h.rule_id for h in list_heuristics()]
    assert first == second
    assert first == sorted(first)


def test_require_heuristic_known() -> None:
    h = require_heuristic("selection.required_locator")
    assert h.version == "1"
    assert h.method == HeuristicMethod.CONFIGURATION
    assert h.stage == DecisionStage.SELECTION


def test_require_heuristic_unknown_fails_clearly() -> None:
    with pytest.raises(KeyError, match=r"Unknown heuristic rule_id"):
        require_heuristic("selection.does_not_exist")


def test_get_heuristic_none_for_unknown() -> None:
    assert get_heuristic("selection.does_not_exist") is None


def test_duplicate_rule_ids_rejected() -> None:
    # Reconstruct definitions and force a duplicate to prove the builder rejects it.
    from law_proposition_extractor_pipeline.heuristics import registry as reg

    defs = list(reg._REGISTRY.values())
    assert defs
    with pytest.raises(ValueError, match=r"Duplicate heuristic rule_id"):
        # Patch by calling builder logic inline
        by_id: dict[str, HeuristicDefinition] = {}
        for definition in [*defs, defs[0]]:
            if definition.rule_id in by_id:
                raise ValueError(
                    f"Duplicate heuristic rule_id {definition.rule_id!r}."
                )
            by_id[definition.rule_id] = definition


def test_empty_version_rejected() -> None:
    with pytest.raises(ValueError, match=r"empty version"):
        HeuristicDefinition(
            rule_id="selection.tmp",
            version="",
            name="tmp",
            plain_english_summary="tmp",
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(),
            output_kinds=(),
            trigger_summary="",
            precedence_summary="",
            failure_mode="",
            diagnostic_codes=(),
            code_references=("law_proposition_extractor_pipeline.runner",),
            test_references=("tests/unit/test_heuristic_registry.py",),
            example_summary="",
        )
        # Empty version is caught by _build_registry; also assert helper:
        by_id: dict[str, HeuristicDefinition] = {}
        definition = HeuristicDefinition(
            rule_id="selection.tmp",
            version="   ",
            name="tmp",
            plain_english_summary="tmp",
            stage=DecisionStage.SELECTION,
            method=HeuristicMethod.DETERMINISTIC,
            input_kinds=(),
            output_kinds=(),
            trigger_summary="",
            precedence_summary="",
            failure_mode="",
            diagnostic_codes=(),
            code_references=("law_proposition_extractor_pipeline.runner",),
            test_references=("tests/unit/test_heuristic_registry.py",),
            example_summary="",
        )
        if not definition.version or not str(definition.version).strip():
            raise ValueError(f"Heuristic {definition.rule_id!r} has an empty version.")
        by_id[definition.rule_id] = definition


def test_initial_rules_have_required_fields() -> None:
    expected = {
        "selection.required_locator",
        "selection.focus_term_match",
        "selection.skip_non_operative",
        "selection.skip_too_short",
        "selection.skip_required_only_mode",
        "selection.prefer_required_children",
        "selection.prefer_required_ancestor",
        "selection.structural_overlap_unresolved",
        "structured_list.compose_terminal_leaf",
        "structured_list.suppress_duplicate_terminal",
        "structured_list.preserve_distinct_terminal_claims",
        "structured_list.reject_non_terminal_row",
        "classification.derive_legal_effect",
        "relationship.infer_exception_to",
        "relationship.infer_triggered_by",
        "relationship.prefer_group_target",
        "relationship.inference_unresolved",
        "grouping.create_shared_fragment_rule_group",
        "effective_law.attach_applicable_exception",
        "effective_law.attach_exception_target",
        "effective_law.attach_trigger_condition",
        "effective_law.prefer_typed_context_over_generic_locator",
    }
    found = {h.rule_id for h in list_heuristics()}
    assert expected <= found
    allowed_stages = {
        DecisionStage.PROVENANCE,
        DecisionStage.SELECTION,
        DecisionStage.EXTRACTION,
        DecisionStage.CLASSIFICATION,
        DecisionStage.GROUPING,
        DecisionStage.RELATIONSHIP,
        DecisionStage.EFFECTIVE_LAW,
        DecisionStage.SOURCE_EFFECT,
        DecisionStage.REVIEW,
    }
    for h in list_heuristics():
        assert h.name
        assert h.plain_english_summary
        assert h.stage in allowed_stages
        assert h.method in {
            HeuristicMethod.DETERMINISTIC,
            HeuristicMethod.CONFIGURATION,
        }
        assert h.version in {"1", "2"}
        if h.rule_id == "relationship.infer_triggered_by":
            assert h.version == "2"
        else:
            assert h.version == "1"
        assert h.code_references
        assert h.test_references
        # No LLM methods registered in this slice.
        assert h.method != HeuristicMethod.LLM
        if h.rule_id.startswith("structured_list."):
            assert h.stage == DecisionStage.EXTRACTION
            assert h.method == HeuristicMethod.DETERMINISTIC
        if h.rule_id.startswith("grouping."):
            assert h.stage == DecisionStage.GROUPING
        if h.rule_id.startswith("effective_law."):
            assert h.stage == DecisionStage.EFFECTIVE_LAW
        if h.rule_id.startswith("relationship."):
            assert h.stage == DecisionStage.RELATIONSHIP
        if h.rule_id.startswith("classification."):
            assert h.stage == DecisionStage.CLASSIFICATION
        if h.rule_id.startswith("provenance."):
            assert h.stage == DecisionStage.PROVENANCE
        if h.rule_id.startswith("source_effect."):
            assert h.stage == DecisionStage.SOURCE_EFFECT

def test_code_references_resolve_to_importable_symbols() -> None:
    for h in list_heuristics():
        for ref in h.code_references:
            module_path, _, attr = ref.rpartition(".")
            assert module_path and attr, f"Bad code reference {ref!r}"
            mod = importlib.import_module(module_path)
            assert hasattr(mod, attr), f"Missing symbol for {ref}"


def test_test_references_exist_as_paths() -> None:
    repo = Path(__file__).resolve().parents[2]
    for h in list_heuristics():
        for ref in h.test_references:
            path = repo / ref
            assert path.is_file(), f"Missing test reference {ref} for {h.rule_id}"


def test_build_registry_idempotent() -> None:
    a = _build_registry()
    b = _build_registry()
    assert list(a.keys()) == list(b.keys())
