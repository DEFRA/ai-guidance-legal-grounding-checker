"""Regression: NPP 2015 reg 2 definition fixture — statutory quotes in evidence_text."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_json_repair import parse_extraction_json
from law_proposition_extractor_pipeline.extraction_workbench import (
    PARSED_EXTRACTION_JSON,
    load_prompt_lab_fixture,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)

SLURRY = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
NPP_REG2 = SLURRY / "slurry-bad-npp-reg-2-definitions.json"


def test_npp_reg2_fixture_schema() -> None:
    data = load_prompt_lab_fixture(NPP_REG2)
    assert data["case_id"] == "slurry-bad-npp-reg-2-definitions"
    assert data["source_record_id"] == "lex-120b4f9c395b3f94"
    assert data["fragment_locator"] == "regulation:2"
    assert data["evaluation"]["mode"] == "minimum"
    assert data["evaluation"]["allow_extra_actual"] is True
    assert len(data["expected_propositions"]) == 4
    subjects = {p["legal_subject"] for p in data["expected_propositions"]}
    assert subjects == {"slurry", "organic manure", "agricultural", "spreading"}
    assert "statutory_quotes_in_evidence_text" in data["expected_challenges"]
    assert "json_parse_unescaped_quotes" in data["expected_challenges"]
    why = data["why_this_case"]
    assert "slurry" in why and "unescaped" in why.lower()
    assert data["dry"]["raw_model_output"]


def test_parse_extraction_json_recovers_four_npp_reg2_definition_rows() -> None:
    data = load_prompt_lab_fixture(NPP_REG2)
    result = parse_extraction_json(data["dry"]["raw_model_output"])
    assert result.json_repair_applied is True
    rows = result.parsed.get("propositions") or []
    assert len(rows) == 4
    subjects = {str(r.get("subject") or "").lower() for r in rows}
    assert subjects == {"slurry", "organic manure", "agricultural", "spreading"}
    assert rows[0]["evidence_text"].startswith('"slurry" means')


def test_dry_workbench_recovers_npp_reg2_statutory_quotes(tmp_path: Path) -> None:
    result = run_extract_fragment_workbench(
        fixture_path=NPP_REG2,
        extraction_mode="dry",
    )
    assert result.workbench_status == "success"
    assert result.actual_proposition_count >= 3
    assert len(result.parsed_extraction_rows) >= 3
    assert not result.empty_reasons

    subjects = {
        str(r.get("subject") or r.get("legal_subject") or "").lower()
        for r in result.parsed_extraction_rows
    }
    for anchor in ("slurry", "organic manure", "agricultural"):
        assert any(anchor in s for s in subjects), f"missing parsed anchor: {anchor}"

    out = write_extract_fragment_workbench_outputs(result, tmp_path / "dry-npp-reg2")
    parsed = json.loads((out / PARSED_EXTRACTION_JSON).read_text(encoding="utf-8"))
    assert parsed, "dry run must not silently produce empty parsed output"

    if result.actual_proposition_count < 4:
        assert any(
            issue.get("kind") == "evidence_traceability" and issue.get("row_index") == 3
            for issue in result.validation_issue_records
        ), "spreading row should fail traceability clearly, not vanish silently"
