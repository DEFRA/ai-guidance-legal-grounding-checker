"""Unit tests for dependent measurement-qualification suppression (20-BR10H)."""

from __future__ import annotations

from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.dependent_qualification import (
    has_independent_legal_effect,
    is_measurement_qualification_row,
    reconcile_dependent_qualification_rows,
)
from law_proposition_extractor_pipeline.heuristics import (
    RULES_EMITTING_DECISION_EXPLANATIONS,
    bind_dependent_qualification_decision_facts,
    build_dependent_qualification_decision_explanations,
    require_heuristic,
)
from law_proposition_extractor_pipeline.heuristics.registry import RULE_SUPPRESS_DEPENDENT_QUALIFICATION
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import load_proposition_fidelity_cases
from law_proposition_extractor_pipeline.proposition_fidelity.runner import evaluate_case
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root
from law_proposition_extractor_pipeline.structured_list_decomposition import StructuredListIdentityContext

_SOURCE = (
    "12. An occupier of a holding must not spread organic manure within 10 metres "
    "of surface water. (1) Paragraph 1 restates the spreading distance for organic "
    "manure. (2) The distance is measured from the edge of the surface water."
)

_IDENTITY = StructuredListIdentityContext(
    source_record_id="src-uk12",
    source_snapshot_id="snap-uk12",
    source_fragment_id="frag-uk12",
)


def _prohibition(**overrides: object) -> dict:
    row = {
        "proposition_text": (
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        "subject": "occupier of a holding",
        "rule": "must not spread organic manure within 10 metres of surface water",
        "object": "organic manure",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:12",
        "evidence_text": (
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "prohibition",
    }
    row.update(overrides)
    return row


def _measurement(**overrides: object) -> dict:
    row = {
        "proposition_text": (
            "The 10-metre spreading distance for organic manure is measured "
            "from the edge of the surface water."
        ),
        "subject": "spreading distance",
        "rule": "is measured from the edge of the surface water",
        "object": "surface water",
        "conditions": [],
        "exceptions": [],
        "provision_type": "definition",
        "source_locator": "regulation:12(2)",
        "evidence_text": "The distance is measured from the edge of the surface water.",
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "measurement",
    }
    row.update(overrides)
    return row


def test_source_grammar_documented_in_fixture() -> None:
    xml = (
        judit_root()
        / "tests/fixtures/structural_source/uk_regulation_headed.xml"
    ).read_text(encoding="utf-8")
    assert "must not spread organic manure within 10 metres of surface water" in xml
    assert "The distance is measured from the edge of the surface water." in xml
    assert "Spreading controls near surface water" in xml


def test_measurement_row_classified_as_dependent_qualification() -> None:
    assert is_measurement_qualification_row(_measurement())
    assert not has_independent_legal_effect(_measurement())
    assert has_independent_legal_effect(_prohibition())
    assert not is_measurement_qualification_row(_prohibition())


def test_suppress_dependent_measurement_preserves_basis() -> None:
    retained, diags, facts = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert len(retained) == 1
    assert "must not spread" in retained[0]["proposition_text"]
    conditions = list(retained[0].get("conditions") or [])
    blob = " ".join([retained[0]["proposition_text"], *conditions]).lower()
    assert "10 metre" in blob or "10 metres" in blob
    assert "edge of the surface water" in blob
    assert diags and diags[0]["code"] == "dependent_qualification_measurement_suppressed"
    assert facts and facts[0]["fact_kind"] == "suppress_dependent_qualification"
    assert facts[0]["retained_candidate_id"]
    assert facts[0]["suppressed_candidate_id"]
    assert facts[0]["retained_candidate_id"] != facts[0]["suppressed_candidate_id"]


def test_input_order_does_not_change_result() -> None:
    a, _, fa = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    b, _, fb = reconcile_dependent_qualification_rows(
        [_measurement(), _prohibition()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert len(a) == len(b) == 1
    assert a[0]["proposition_text"] == b[0]["proposition_text"]
    assert {f["suppressed_candidate_id"] for f in fa} == {
        f["suppressed_candidate_id"] for f in fb
    }


def test_same_source_and_snapshot_required() -> None:
    retained, diags, facts = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=StructuredListIdentityContext(
            source_record_id="",
            source_snapshot_id="snap",
            source_fragment_id="frag",
        ),
    )
    assert len(retained) == 2
    assert not diags and not facts


def test_different_snapshot_not_suppressed() -> None:
    # Identity is scoped per call; simulate cross-snapshot by empty fragment.
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=StructuredListIdentityContext(
            source_record_id="src",
            source_snapshot_id="snap-a",
            source_fragment_id="",
        ),
    )
    assert len(retained) == 2


def test_non_overlapping_evidence_from_other_fragment_not_suppressed() -> None:
    other = _measurement(
        evidence_text="Completely unrelated evidence about tidal waters.",
        source_locator="regulation:99",
        proposition_text="The distance is measured from the edge of tidal waters.",
    )
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), other],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert len(retained) == 2


def test_independent_measurement_obligation_not_suppressed() -> None:
    duty = {
        "proposition_text": (
            "The operator must measure the distance before spreading."
        ),
        "subject": "The operator",
        "rule": "must measure the distance before spreading",
        "object": "distance",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:12(2)",
        "evidence_text": "The operator must measure the distance before spreading.",
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "independent duty",
    }
    source = _SOURCE + " The operator must measure the distance before spreading."
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), duty],
        source_text=source,
        identity=_IDENTITY,
    )
    assert len(retained) == 2
    assert any("must measure" in r["proposition_text"] for r in retained)


def test_recordkeeping_duty_not_suppressed() -> None:
    duty = {
        "proposition_text": "The operator must record the measured distance.",
        "subject": "The operator",
        "rule": "must record the measured distance",
        "object": "measured distance",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:12(3)",
        "evidence_text": "The operator must record the measured distance.",
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "recordkeeping",
    }
    source = _SOURCE + " The operator must record the measured distance."
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), duty],
        source_text=source,
        identity=_IDENTITY,
    )
    assert len(retained) == 2


def test_exception_not_suppressed() -> None:
    exc = {
        "proposition_text": (
            "Paragraph 1 shall not apply where the measured distance exceeds "
            "50 metres from a dwelling."
        ),
        "subject": "Paragraph 1",
        "rule": "shall not apply where the measured distance exceeds 50 metres",
        "object": "dwelling",
        "conditions": [],
        "exceptions": [],
        "provision_type": "exception",
        "source_locator": "regulation:12(3)",
        "evidence_text": (
            "Paragraph 1 shall not apply where the measured distance exceeds "
            "50 metres from a dwelling."
        ),
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "exception",
    }
    source = _SOURCE + " " + exc["evidence_text"]
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), exc],
        source_text=source,
        identity=_IDENTITY,
    )
    assert len(retained) == 2


def test_missing_preservation_prevents_suppression() -> None:
    gov = _prohibition(
        proposition_text="An occupier of a holding must not spread organic manure.",
        rule="must not spread organic manure",
        evidence_text="An occupier of a holding must not spread organic manure.",
    )
    # Measurement about a different numeric regime with no shared threshold.
    meas = _measurement(
        proposition_text="The 50-metre buffer is measured from the edge of the surface water.",
        evidence_text="The 50-metre buffer is measured from the edge of the surface water.",
        source_locator="regulation:99",
    )
    source = (
        "An occupier of a holding must not spread organic manure. "
        "The 50-metre buffer is measured from the edge of the surface water."
    )
    retained, _, _ = reconcile_dependent_qualification_rows(
        [gov, meas],
        source_text=source,
        identity=_IDENTITY,
    )
    assert len(retained) == 2


def test_ambiguous_multiple_governors_not_silently_suppressed() -> None:
    # Two governors with identical operative rank signals (same modal/actor/
    # threshold shape); only proposition text differs by a synonym.
    p1 = _prohibition(
        proposition_text=(
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water near field A."
        ),
        evidence_text=(
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water near field A."
        ),
        source_locator="regulation:12",
    )
    p2 = _prohibition(
        proposition_text=(
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water near field B."
        ),
        evidence_text=(
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water near field B."
        ),
        source_locator="regulation:12",
    )
    source = (
        "An occupier of a holding must not spread organic manure within "
        "10 metres of surface water near field A. "
        "An occupier of a holding must not spread organic manure within "
        "10 metres of surface water near field B. "
        "The distance is measured from the edge of the surface water."
    )
    retained, _, facts = reconcile_dependent_qualification_rows(
        [p1, p2, _measurement()],
        source_text=source,
        identity=_IDENTITY,
    )
    # Equal-rank governors → do not silently pick a winner for suppression.
    assert len(retained) == 3
    assert not facts


def test_decision_ids_deterministic() -> None:
    _, _, f1 = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    _, _, f2 = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert f1[0]["suppressed_candidate_id"] == f2[0]["suppressed_candidate_id"]
    assert f1[0]["retained_candidate_id"] == f2[0]["retained_candidate_id"]


def test_explainability_rule_registered() -> None:
    rule = require_heuristic(RULE_SUPPRESS_DEPENDENT_QUALIFICATION)
    assert rule.version == "1"
    assert RULE_SUPPRESS_DEPENDENT_QUALIFICATION in RULES_EMITTING_DECISION_EXPLANATIONS
    retained, _, facts = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    props = [
        {
            "id": "prop-001",
            "extraction_debug_meta": {
                "extraction_candidate_id": facts[0]["retained_candidate_id"]
            },
        }
    ]
    bound = bind_dependent_qualification_decision_facts(facts, propositions=props)
    expls = build_dependent_qualification_decision_explanations(bound)
    assert len(expls) == 1
    assert expls[0].rule_id == RULE_SUPPRESS_DEPENDENT_QUALIFICATION
    assert "no independent legal effect" in expls[0].summary
    assert expls[0].metadata["retained_proposition_id"] == "prop-001"
    assert expls[0].subject_id == facts[0]["suppressed_candidate_id"]


def test_live_shaped_rows_suppress_via_reconcile() -> None:
    retained, diags, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert len(retained) == 1
    assert diags
    blob = " ".join(
        [
            retained[0]["proposition_text"],
            " ".join(str(x) for x in (retained[0].get("conditions") or [])),
        ]
    ).lower()
    assert "10" in blob
    assert "edge" in blob


def test_offline_uk_regulation_12_fixture_still_one_prop(tmp_path: Path) -> None:
    case = next(
        c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread"
    )
    result = evaluate_case(case, work_dir=tmp_path)
    assert result.produced_count == 1
    assert result.matched_roles == ["organic-manure-spread-prohibition"]
    assert result.unexpected_propositions == []


def test_compound_independent_measurement_obligation_survives(tmp_path: Path) -> None:
    case = next(
        c
        for c in load_proposition_fidelity_cases()
        if c.case_id == "uk_compound_spread_and_measure"
    )
    result = evaluate_case(case, work_dir=tmp_path)
    assert result.produced_count == 2
    assert set(result.matched_roles) == {
        "organic-manure-spread-prohibition",
        "distance-measurement-restatement",
    }


# --- mutations ---


def test_mutation_measurement_basis_lost_from_retained() -> None:
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    conditions = list(retained[0].get("conditions") or [])
    blob = " ".join([retained[0]["proposition_text"], *conditions]).lower()
    assert "edge of the surface water" in blob, (
        "legal-effect defect: measurement basis must remain on the retained "
        "governing prohibition after dependent-qualification suppression"
    )
    # Mutation: drop preserved conditions — must fail the invariant.
    mutated = dict(retained[0])
    mutated["conditions"] = []
    mutated_blob = " ".join(
        [mutated["proposition_text"], *list(mutated.get("conditions") or [])]
    ).lower()
    with pytest.raises(AssertionError):
        assert "edge of the surface water" in mutated_blob


def test_mutation_dependent_row_retained() -> None:
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    with pytest.raises(AssertionError):
        assert len(retained) == 2, (
            "proposition-boundary defect: dependent measurement qualification "
            "must not survive as a standalone legal proposition"
        )


def test_mutation_independent_obligation_suppressed() -> None:
    duty = {
        "proposition_text": "The operator must measure the distance before spreading.",
        "subject": "operator",
        "rule": "must measure the distance before spreading",
        "object": "distance",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:12(2)",
        "evidence_text": "The operator must measure the distance before spreading.",
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "duty",
    }
    source = _SOURCE + " The operator must measure the distance before spreading."
    retained, _, _ = reconcile_dependent_qualification_rows(
        [_prohibition(), duty],
        source_text=source,
        identity=_IDENTITY,
    )
    assert len(retained) == 2
    with pytest.raises(AssertionError):
        assert len(retained) == 1, (
            "legal-effect defect: independent measurement obligation must not "
            "be suppressed as a dependent qualification"
        )


def test_mutation_wrong_retained_explanation_target() -> None:
    retained, _, facts = reconcile_dependent_qualification_rows(
        [_prohibition(), _measurement()],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    wrong = dict(facts[0])
    wrong["retained_candidate_id"] = "extractcand:not-the-winner"
    props = [
        {
            "id": "prop-001",
            "extraction_debug_meta": {
                "extraction_candidate_id": facts[0]["retained_candidate_id"]
            },
        }
    ]
    bound = bind_dependent_qualification_decision_facts([wrong], propositions=props)
    expls = build_dependent_qualification_decision_explanations(bound)
    with pytest.raises(AssertionError):
        assert expls[0].metadata.get("retained_proposition_id") == "prop-001", (
            "explainability defect: suppression must point at the retained "
            "governing proposition"
        )


def test_mutation_suppression_without_evidence_overlap() -> None:
    other = _measurement(
        evidence_text="Unrelated span about coastal waters elsewhere.",
        proposition_text="The distance is measured from coastal waters.",
        source_locator="regulation:50",
    )
    retained, _, facts = reconcile_dependent_qualification_rows(
        [_prohibition(), other],
        source_text=_SOURCE,
        identity=_IDENTITY,
    )
    assert len(retained) == 2
    assert not facts
    with pytest.raises(AssertionError):
        assert facts, (
            "proposition-boundary defect: suppression must require evidence "
            "containment/overlap or linked same-fragment spans"
        )
