"""Unit tests for dense-fragment anchor detection and coverage (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.extraction_workbench import load_prompt_lab_fixture
from law_proposition_extractor_pipeline.fragment_anchor_coverage import (
    NPP_REG2_REQUIRED_ANCHORS,
    anchor_is_covered,
    check_fragment_anchor_coverage,
    classify_anchor_severity,
    dedupe_anchors,
    detect_anchors_from_fragment_text,
    is_dense_fragment,
    proposition_coverage_haystack,
    summarize_export_fragment_anchor_coverage,
    summarize_npp_reg2_definition_anchors,
)

SLURRY_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "extraction_prompt_cases"
    / "slurry"
    / "slurry-bad-npp-reg-2-definitions.json"
)
PROMPT_LAB_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "runs"
    / "prompt-lab"
    / "repair-npp-2015-reg-2-dry-fixture.json"
)


@pytest.fixture
def npp_reg2_fragment_text() -> str:
    data = load_prompt_lab_fixture(SLURRY_FIXTURE)
    return str(data["fragment_text"])


def test_prompt_lab_dry_fixture_points_at_npp_reg2() -> None:
    if not PROMPT_LAB_FIXTURE.is_file():
        pytest.skip("prompt-lab dry fixture not present locally")
    payload = json.loads(PROMPT_LAB_FIXTURE.read_text(encoding="utf-8"))
    assert payload["source_id"] == "lex-120b4f9c395b3f94"
    assert payload["locator"] == "regulation:2"


def test_detect_npp_reg2_definition_anchors_from_fragment_text(
    npp_reg2_fragment_text: str,
) -> None:
    anchors = detect_anchors_from_fragment_text(npp_reg2_fragment_text)
    labels = {a.label for a in anchors if a.category == "definition"}
    for required in NPP_REG2_REQUIRED_ANCHORS:
        assert any(required in label for label in labels), f"missing detected anchor: {required}"


def test_dense_fragment_heuristic(npp_reg2_fragment_text: str) -> None:
    detected = detect_anchors_from_fragment_text(npp_reg2_fragment_text)
    assert is_dense_fragment(npp_reg2_fragment_text, detected)


def test_anchor_covered_via_evidence_quote() -> None:
    row = {
        "proposition_text": "Definition row",
        "label": "Definition: slurry",
        "legal_subject": "slurry",
        "extraction_debug_meta": {
            "evidence_quote": '"slurry" means excreta produced by livestock',
        },
    }
    hay = proposition_coverage_haystack(row)
    from law_proposition_extractor_pipeline.fragment_anchor_coverage import DetectedAnchor

    anchor = DetectedAnchor(
        anchor_id="definition:means:slurry",
        category="definition",
        label="slurry",
        source_excerpt='"slurry" means',
        search_terms=("slurry", '"slurry" means'),
    )
    assert anchor_is_covered(anchor, hay)


def test_reg2_coverage_empty_propositions_needs_review(npp_reg2_fragment_text: str) -> None:
    report = check_fragment_anchor_coverage(
        source_record_id="lex-120b4f9c395b3f94",
        source_fragment_id="frag-reg2",
        fragment_locator="regulation:2",
        fragment_text=npp_reg2_fragment_text,
        proposition_rows=[],
    )
    assert report.dense
    assert report.missing
    assert any("slurry" in a.label for a in report.missing)


def test_reg2_coverage_with_expected_rows(npp_reg2_fragment_text: str) -> None:
    data = load_prompt_lab_fixture(SLURRY_FIXTURE)
    rows = []
    for idx, expected in enumerate(data["expected_propositions"]):
        rows.append(
            {
                "id": f"prop-{idx}",
                "source_record_id": data["source_record_id"],
                "fragment_locator": data["fragment_locator"],
                "proposition_text": expected["proposition_text"],
                "label": expected.get("legal_subject", ""),
                "legal_subject": expected["legal_subject"],
                "action": expected["action"],
                "affected_subjects": expected.get("affected_subjects", []),
                "conditions": expected.get("conditions", []),
                "exceptions": expected.get("exceptions", []),
                "required_documents": expected.get("required_documents", []),
                "extraction_debug_meta": {"evidence_quote": expected["evidence_quote"]},
            }
        )
    report = check_fragment_anchor_coverage(
        source_record_id=data["source_record_id"],
        source_fragment_id="frag-reg2",
        fragment_locator=data["fragment_locator"],
        fragment_text=npp_reg2_fragment_text,
        proposition_rows=rows,
    )
    assert report.dense
    summary = summarize_npp_reg2_definition_anchors(rows)
    assert summary["all_present"] is True


def test_summarize_export_bundle_with_fragment(npp_reg2_fragment_text: str) -> None:
    data = load_prompt_lab_fixture(SLURRY_FIXTURE)
    bundle = {
        "source_fragments": [
            {
                "id": "frag-reg2",
                "source_record_id": data["source_record_id"],
                "locator": "regulation:2",
                "fragment_text": npp_reg2_fragment_text,
            }
        ],
        "propositions": [
            {
                "id": "prop-slurry",
                "source_record_id": data["source_record_id"],
                "fragment_locator": "regulation:2",
                "proposition_text": '"slurry" means excreta.',
                "legal_subject": "slurry",
                "extraction_debug_meta": {"evidence_quote": '"slurry" means'},
            }
        ],
    }
    summary = summarize_export_fragment_anchor_coverage(bundle)
    assert summary["dense_fragments"] == 1
    assert summary["npp_reg2"]["anchors"]["slurry"]["present"] is True
    assert summary["missing_diagnostic_count"] >= 1 or summary["missing_important_count"] >= 1


def test_livestock_category_anchors_are_diagnostic() -> None:
    text = "Table 1 cattle sheep pigs poultry 170 kg N per hectare per year"
    anchors = detect_anchors_from_fragment_text(text)
    livestock = [a for a in anchors if a.detector_id == "livestock_category"]
    assert livestock
    for anchor in livestock:
        assert (
            classify_anchor_severity(
                anchor,
                source_record_id="lex-test",
                fragment_locator="schedule:1",
            )
            == "diagnostic"
        )


def test_core_definition_anchors_are_critical() -> None:
    text = '"slurry" means excreta; "organic manure" means fertiliser.'
    anchors = detect_anchors_from_fragment_text(text)
    defs = [a for a in anchors if a.category == "definition"]
    assert any(
        classify_anchor_severity(
            a,
            source_record_id="lex-120b4f9c395b3f94",
            fragment_locator="regulation:2",
        )
        == "critical"
        for a in defs
    )


def test_dedupe_anchors_by_locator_label_category() -> None:
    anchors = detect_anchors_from_fragment_text("cattle cattle cattle pigs pigs")
    deduped = dedupe_anchors(
        anchors,
        source_record_id="lex-test",
        fragment_locator="schedule:1",
    )
    labels = [a.label for a in deduped if a.detector_id == "livestock_category"]
    assert labels.count("cattle") == 1
    assert labels.count("pigs") == 1


def test_summarize_includes_severity_breakdown(npp_reg2_fragment_text: str) -> None:
    data = load_prompt_lab_fixture(SLURRY_FIXTURE)
    bundle = {
        "source_fragments": [
            {
                "id": "frag-reg2",
                "source_record_id": data["source_record_id"],
                "locator": "regulation:2",
                "fragment_text": npp_reg2_fragment_text,
            }
        ],
        "propositions": [],
    }
    summary = summarize_export_fragment_anchor_coverage(bundle)
    assert "missing_by_severity" in summary
    assert "missing_critical_count" in summary
    assert "diagnostic_table_noise_summary" in summary
