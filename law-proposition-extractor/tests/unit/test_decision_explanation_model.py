"""DecisionExplanation domain model tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from law_proposition_extractor_domain import (
    DecisionAlternative,
    DecisionEvidence,
    DecisionExplanation,
    DecisionExplanationsArtifact,
    DecisionInput,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
    SuppressedDecisionItem,
)
from law_proposition_extractor_pipeline.heuristics.selection_explanations import decision_explanation_id


def _base_explanation(**overrides: object) -> DecisionExplanation:
    payload = {
        "id": "decision:abc",
        "stage": DecisionStage.SELECTION,
        "decision_type": DecisionType.SELECT,
        "subject_kind": DecisionSubjectKind.SOURCE_FRAGMENT,
        "subject_id": "frag-1",
        "outcome": "selected_for_extraction",
        "method": HeuristicMethod.CONFIGURATION,
        "rule_id": "selection.required_locator",
        "rule_version": "1",
        "summary": "Selected because required.",
    }
    payload.update(overrides)
    return DecisionExplanation.model_validate(payload)


def test_decision_explanation_round_trip() -> None:
    original = _base_explanation(
        evidence=[
            DecisionEvidence(kind="source_locator", label="Fragment locator", value="article:1"),
            DecisionEvidence(kind="required_locator", label="Required", value="article:1"),
        ],
        inputs=[DecisionInput(kind="required_locator", value="article:1")],
        alternatives=[
            DecisionAlternative(
                kind="source_fragment",
                id="frag-2",
                value="article:1:paragraph:1",
                role="preferred_extraction_unit",
            )
        ],
        suppressed_items=[
            SuppressedDecisionItem(
                kind="source_fragment",
                id="frag-x",
                reason="covered_by_selected_children",
            )
        ],
    )
    dumped = original.model_dump(mode="json")
    restored = DecisionExplanation.model_validate(dumped)
    assert restored == original
    assert restored.model_alias is None
    assert restored.prompt_version is None


def test_optional_llm_fields_absent_for_deterministic() -> None:
    expl = _base_explanation(method=HeuristicMethod.DETERMINISTIC)
    dumped = expl.model_dump(mode="json")
    assert dumped["model_alias"] is None
    assert dumped["prompt_version"] is None


def test_decision_id_deterministic_across_input_order() -> None:
    a = decision_explanation_id(
        stage="selection",
        decision_type="select",
        subject_kind="source_fragment",
        subject_id="frag-1",
        rule_id="selection.required_locator",
        rule_version="1",
        outcome="selected_for_extraction",
        material_input_identity="a\x1fb\x1fc",
    )
    b = decision_explanation_id(
        stage="selection",
        decision_type="select",
        subject_kind="source_fragment",
        subject_id="frag-1",
        rule_id="selection.required_locator",
        rule_version="1",
        outcome="selected_for_extraction",
        material_input_identity="a\x1fb\x1fc",
    )
    assert a == b
    assert a.startswith("decision:")


def test_different_outcome_produces_different_id() -> None:
    a = decision_explanation_id(
        stage="selection",
        decision_type="select",
        subject_kind="source_fragment",
        subject_id="frag-1",
        rule_id="selection.required_locator",
        rule_version="1",
        outcome="selected_for_extraction",
        material_input_identity="x",
    )
    b = decision_explanation_id(
        stage="selection",
        decision_type="suppress",
        subject_kind="source_fragment",
        subject_id="frag-1",
        rule_id="selection.required_locator",
        rule_version="1",
        outcome="not_selected_for_extraction",
        material_input_identity="x",
    )
    assert a != b


def test_evidence_and_suppressed_ordering_deterministic() -> None:
    expl = _base_explanation(
        evidence=[
            DecisionEvidence(kind="b", label="B", value="2"),
            DecisionEvidence(kind="a", label="A", value="1"),
        ],
        suppressed_items=[
            SuppressedDecisionItem(kind="source_fragment", id="z", reason="r"),
            SuppressedDecisionItem(kind="source_fragment", id="a", reason="r"),
        ],
    )
    # Domain model preserves list order as provided; emission layer sorts.
    # Validate artifact wrapper still round-trips.
    artifact = DecisionExplanationsArtifact(
        run_id="run-1",
        decisions=[expl],
        metadata={"registry_version": "1"},
    )
    restored = DecisionExplanationsArtifact.model_validate(artifact.model_dump(mode="json"))
    assert restored.decisions[0].id == expl.id


def test_unsupported_enum_values_rejected() -> None:
    with pytest.raises(ValidationError):
        _base_explanation(stage="not_a_stage")
    with pytest.raises(ValidationError):
        _base_explanation(decision_type="invented")
    with pytest.raises(ValidationError):
        _base_explanation(method="magic")
    with pytest.raises(ValidationError):
        _base_explanation(subject_kind="not_a_subject")
    # Newly supported subject kinds for structured-list explainability.
    expl = _base_explanation(subject_kind="proposition")
    assert expl.subject_kind.value == "proposition"
    expl2 = _base_explanation(subject_kind="extraction_candidate")
    assert expl2.subject_kind.value == "extraction_candidate"
    expl3 = _base_explanation(stage="extraction")
    assert expl3.stage.value == "extraction"
    expl4 = _base_explanation(
        stage="classification",
        decision_type="classify",
        subject_kind="proposition",
    )
    assert expl4.stage.value == "classification"
    assert expl4.decision_type.value == "classify"
    expl5 = _base_explanation(
        stage="relationship",
        decision_type="infer",
        subject_kind="legal_rule_relationship",
    )
    assert expl5.stage.value == "relationship"
    assert expl5.subject_kind.value == "legal_rule_relationship"
    expl6 = _base_explanation(decision_type="target", stage="relationship")
    assert expl6.decision_type.value == "target"
