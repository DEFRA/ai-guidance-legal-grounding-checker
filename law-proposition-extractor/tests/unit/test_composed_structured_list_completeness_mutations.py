"""Mutation tests for composed structured-list completeness reconciliation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.composed_structured_list_completeness import (
    RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
    RECONCILIATION_BASIS,
    reconcile_composed_structured_list_completeness,
)
from law_proposition_extractor_pipeline.heuristics import (
    bind_completeness_reconciliation_decision_facts,
    build_completeness_reconciliation_decision_explanations,
)
from law_proposition_extractor_pipeline.proposition_completeness import build_proposition_completeness_assessments
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    COMPOSITION_BASIS,
    StructuredListIdentityContext,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.paths import (
    CALIBRATION_CASES,
    REPETITIONS,
    call_artifact_name,
    calls_dir,
    run_dir,
)

_IDENTITY = StructuredListIdentityContext("src", "snap", "frag")
_LIVE_RUN = "live-pf-20260715T155907Z"


def _e2_row(**overrides: object) -> dict:
    row = {
        "proposition_text": (
            "Paragraph 1 of Article 49a shall not apply where the catches "
            "contain more than 80% of one or more species used for industrial "
            "purposes, namely capelin, sandeel, or Norwegian pout."
        ),
        "subject": "Paragraph 1 of Article 49a",
        "rule": "shall not apply",
        "object": "stowage",
        "conditions": [],
        "exceptions": [],
        "provision_type": "exception",
        "source_locator": "article:49a:paragraph:2:list:2-a-ii",
        "evidence_text": "capelin, sandeel, Norwegian pout",
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": "stem carried forward",
        "_structured_list_compose_captured": True,
        "_composition_basis": COMPOSITION_BASIS,
        "_extraction_candidate_id": "extractcand:e2",
        "_structured_list_meta": {
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "(2) Paragraph 1 shall not apply:",
            "branch_context": (
                "where the catches contain more than 80% of one or more of "
                "the following species"
            ),
            "list_marker": "(a)(ii)",
            "structured_list_path": "2-a-ii",
            "source_component_locators": [
                {"role": "stem", "text": "(2) Paragraph 1 shall not apply:"},
                {
                    "role": "branch",
                    "text": (
                        "where the catches contain more than 80% of one or "
                        "more of the following species"
                    ),
                },
                {
                    "role": "leaf",
                    "text": "capelin, sandeel, Norwegian pout (industrial)",
                },
            ],
        },
    }
    row.update(overrides)
    return row


def test_mutation_e2_must_not_remain_context_dependent_after_verified_composition() -> None:
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [_e2_row()], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "complete", (
        "completeness-unit: E2 remained context_dependent after verified "
        "structured-list composition"
    )
    assert facts, "structured-composition: expected reconciliation fact for E2"


def test_mutation_e2_must_not_complete_without_governing_stem() -> None:
    row = _e2_row(
        proposition_text=(
            "Where the catches contain more than 80% of capelin, sandeel, or "
            "Norwegian pout."
        ),
        rule="",
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "completeness-unit: E2 became complete without governing stem in text"
    )
    assert not facts


def test_mutation_e2_must_not_complete_with_unresolved_missing_context() -> None:
    row = _e2_row(missing_context=["cross_reference"])
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "completeness-unit: E2 became complete with unresolved missing_context"
    )
    assert not facts


def test_mutation_e2_text_not_rewritten() -> None:
    row = _e2_row()
    original = row["proposition_text"]
    retained, _, _ = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["proposition_text"] == original, (
        "structured-composition: reconciliation rewrote E2 proposition text"
    )


def test_mutation_e2_id_stable_when_completeness_changes() -> None:
    row = _e2_row()
    cid = row["_extraction_candidate_id"]
    retained, _, _ = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["_extraction_candidate_id"] == cid, (
        "completeness-unit: candidate/proposition identity changed because "
        "completeness changed"
    )


def test_mutation_wsi_36_4_not_reconciled() -> None:
    row = {
        "proposition_text": (
            "The occupier must make a record of the calculations and how the "
            "final figures were arrived at."
        ),
        "subject": "occupier",
        "rule": "must make a record",
        "object": "the calculations",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "regulation:36(4)",
        "evidence_text": "record of the calculations",
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": "anaphora",
        "_structured_list_compose_captured": True,
        "_composition_basis": COMPOSITION_BASIS,
        "_structured_list_meta": {
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "The occupier must make a record:",
            "branch_context": "",
            "structured_list_path": "36-4",
            "source_component_locators": [
                {"role": "stem", "text": "The occupier must make a record:"},
                {
                    "role": "leaf",
                    "text": "of the calculations and how the final figures were arrived at",
                },
            ],
        },
    }
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "completeness-unit: WSI 36(4) incorrectly reconciled"
    )
    assert not facts


def test_mutation_p3_not_reconciled() -> None:
    row = {
        "proposition_text": (
            "Where the cases referred to in paragraph 2 apply, a fisheries "
            "administration must monitor the catch composition."
        ),
        "subject": "fisheries administration",
        "rule": "must monitor",
        "object": "catch composition",
        "conditions": [],
        "exceptions": [],
        "provision_type": "core",
        "source_locator": "article:49a:paragraph:3",
        "evidence_text": "cases referred to in paragraph 2",
        "completeness_status": "context_dependent",
        "confidence": "high",
        "reason": "P3 depends on paragraph 2",
        "_structured_list_compose_captured": False,
    }
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "completeness-unit: P3 incorrectly reconciled"
    )
    assert not facts


def test_mutation_intermediate_list_node_not_completed() -> None:
    row = _e2_row(
        proposition_text=(
            "Paragraph 1 shall not apply where the catches contain more than "
            "80% of one or more of the following species"
        ),
        _structured_list_meta={
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": "Paragraph 1 shall not apply:",
            "branch_context": (
                "where the catches contain more than 80% of one or more of "
                "the following species"
            ),
            "structured_list_path": "2-a",
            "source_component_locators": [
                {"role": "stem", "text": "Paragraph 1 shall not apply:"},
                {
                    "role": "branch",
                    "text": (
                        "where the catches contain more than 80% of one or "
                        "more of the following species"
                    ),
                },
            ],
        },
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "structured-composition: intermediate list node became complete"
    )
    assert not facts


def test_mutation_model_status_provenance_retained() -> None:
    retained, _, _ = reconcile_composed_structured_list_completeness(
        [_e2_row()], identity=_IDENTITY
    )
    assert retained[0].get("model_completeness_status") == "context_dependent", (
        "completeness-unit: model status provenance erased"
    )
    assert retained[0].get("model_reason"), (
        "completeness-unit: model_reason provenance erased"
    )


def test_mutation_explanation_includes_basis() -> None:
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [_e2_row()], identity=_IDENTITY
    )
    bound = bind_completeness_reconciliation_decision_facts(
        facts,
        propositions=[
            {
                "id": "prop-e2",
                "extraction_debug_meta": {
                    "extraction_candidate_id": retained[0]["_extraction_candidate_id"]
                },
            }
        ],
    )
    expls = build_completeness_reconciliation_decision_explanations(bound)
    assert expls, "completeness-unit: reconciliation explanation missing"
    assert any(
        e.kind == "reconciliation_basis" and RECONCILIATION_BASIS in str(e.value)
        for e in expls[0].evidence
    ), "completeness-unit: reconciliation explanation omits its basis"
    assert expls[0].metadata.get("model_completeness_status") == "context_dependent"


def test_mutation_pca_and_proposition_completeness_agree() -> None:
    retained, _, _ = reconcile_composed_structured_list_completeness(
        [_e2_row()], identity=_IDENTITY
    )
    prop = {
        "id": "prop-e2",
        "proposition_text": retained[0]["proposition_text"],
        "extraction_debug_meta": {
            "completeness_status": retained[0]["completeness_status"],
            "model_completeness_status": retained[0]["model_completeness_status"],
            "parent_context": retained[0]["_structured_list_meta"]["parent_context"],
            "composition_basis": COMPOSITION_BASIS,
            "list_marker": "(a)(ii)",
            "structured_list_path": "2-a-ii",
        },
    }
    pca = build_proposition_completeness_assessments(
        propositions=[prop],
        proposition_extraction_traces=[
            {
                "proposition_id": "prop-e2",
                "signals": {
                    "parent_context": prop["extraction_debug_meta"]["parent_context"],
                    "composition_basis": COMPOSITION_BASIS,
                    "list_marker": "(a)(ii)",
                },
            }
        ],
        source_records=[],
    )
    assert retained[0]["completeness_status"] == "complete"
    assert pca[0].status == "complete", (
        "completeness-unit: PCA and proposition completeness disagree after "
        f"reconciliation (prop={retained[0]['completeness_status']} pca={pca[0].status})"
    )


def test_mutation_fidelity_reads_reconciled_not_raw_model() -> None:
    from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import _debug_meta

    prop = {
        "id": "prop-e2",
        "proposition_text": _e2_row()["proposition_text"],
        "extraction_debug_meta": {
            "completeness_status": "complete",
            "model_completeness_status": "context_dependent",
            "structured_list_path": "2-a-ii",
        },
    }
    meta = _debug_meta(prop)
    actual = str(meta.get("completeness_status") or "")
    model = str(meta.get("model_completeness_status") or "")
    assert actual == "complete", (
        "completeness-unit: fidelity still reads raw model completeness "
        f"(actual={actual} model={model})"
    )
    assert model == "context_dependent"
    assert actual != model


def test_mutation_sibling_parity_does_not_force_invalid_status() -> None:
    good = _e2_row()
    bad = _e2_row(
        proposition_text="capelin only leaf without stem",
        rule="",
        _extraction_candidate_id="extractcand:bad",
        _structured_list_meta={
            **_e2_row()["_structured_list_meta"],
            "structured_list_path": "2-a-i",
        },
    )
    retained, diags, _ = reconcile_composed_structured_list_completeness(
        [good, bad], identity=_IDENTITY
    )
    by_path = {
        str((r.get("_structured_list_meta") or {}).get("structured_list_path")): r
        for r in retained
    }
    assert by_path["2-a-ii"]["completeness_status"] == "complete"
    assert by_path["2-a-i"]["completeness_status"] == "context_dependent", (
        "completeness-unit: sibling parity check forced an invalid status"
    )
    # Diagnostic may be present; status must not be forced.
    assert by_path["2-a-i"].get("reconciliation_applied") not in {True, "true"}


def test_mutation_heading_text_does_not_satisfy_operative_context() -> None:
    row = _e2_row(
        proposition_text="Industrial fisheries exception",
        display_label=(
            "Paragraph 1 shall not apply — capelin, sandeel, Norwegian pout — 80%"
        ),
        rule="",
    )
    retained, _, facts = reconcile_composed_structured_list_completeness(
        [row], identity=_IDENTITY
    )
    assert retained[0]["completeness_status"] == "context_dependent", (
        "completeness-unit: heading text satisfied missing operative context"
    )
    assert not facts


@pytest.mark.skipif(
    not (judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN).is_dir(),
    reason="live calibration artifacts absent",
)
def test_mutation_historical_calibration_artifacts_unchanged() -> None:
    base = run_dir(_LIVE_RUN)
    paths = [
        base / "calibration_result.json",
        base / "calibration_report.md",
        base / "calibration_manifest.json",
    ]
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            paths.append(calls_dir(_LIVE_RUN) / call_artifact_name(case_id, rep))
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    # Reconcile alone must not touch disk artifacts.
    reconcile_composed_structured_list_completeness([_e2_row()], identity=_IDENTITY)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    assert before == after, (
        "completeness-unit: historical calibration artifacts were overwritten"
    )
