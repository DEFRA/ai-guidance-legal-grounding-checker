"""Unit tests for fresh extraction export verification."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.fresh_extraction_verification import (
    VERIFICATION_JSON_FILENAME,
    VERIFICATION_MD_FILENAME,
    build_fresh_extraction_verification,
    verification_exit_code,
    write_fresh_extraction_verification,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "fresh_extraction_verification"
OK_EXPORT = FIXTURE_ROOT / "minimal_ok"


@pytest.fixture
def ok_export(tmp_path: Path) -> Path:
    dest = tmp_path / "export"
    shutil.copytree(OK_EXPORT, dest)
    return dest


def test_minimal_ok_export_passes(ok_export: Path) -> None:
    report = build_fresh_extraction_verification(ok_export)
    assert report.proposition_count == 4
    assert report.hard_failure is False
    assert report.error_count == 0
    assert verification_exit_code(report) == 0
    assert report.counts["compliance_relevant"] == 3
    anchors = {a.anchor: a for a in report.prompt_lab_anchors}
    assert anchors["regulation 8"].proposition_count == 1
    assert anchors["regulation 17"].proposition_count == 1
    assert anchors["Schedule 1"].proposition_count == 1
    assert anchors["regulation 6"].proposition_count == 1


def test_missing_propositions_json_hard_fails(tmp_path: Path) -> None:
    export = tmp_path / "empty"
    export.mkdir()
    (export / "MODEL.md").write_text("# test\n", encoding="utf-8")
    report = build_fresh_extraction_verification(export)
    assert report.hard_failure is True
    assert report.error_count >= 1
    assert verification_exit_code(report) == 1


def test_debug_leakage_in_review_notes_hard_fails(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["review_notes"] = 'judit_extraction_meta:{"leaked": true}'
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert report.hard_failure is True
    assert any(f.check_id == "debug_leakage" for f in report.findings)


def test_dangerous_legacy_key_hard_fails(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["cross_reference_key"] = "uk:these-regulations:must-ensure"
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert report.hard_failure is True
    assert any(f.check_id == "dangerous_legacy_relationship_key" for f in report.findings)


def test_missing_tier_hard_fails(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["proposition_tier"] = ""
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert report.hard_failure is True
    assert any(f.check_id == "missing_proposition_tier" for f in report.findings)


def test_unknown_tier_warns_not_hard_fails(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["proposition_tier"] = "unknown"
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert report.hard_failure is False
    assert any(f.check_id == "unknown_proposition_tier" for f in report.findings)
    assert verification_exit_code(report) == 0
    assert verification_exit_code(report, strict=True) == 1


def test_missing_evidence_warns(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["extraction_debug_meta"] = {"model_confidence": "high"}
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert any(f.check_id == "missing_evidence_quote" for f in report.findings)
    assert report.evidence_health["missing_evidence_quote_count"] >= 1


def test_categories_only_obligation_signal_warns(ok_export: Path) -> None:
    rows = json.loads((ok_export / "propositions.json").read_text(encoding="utf-8"))
    rows[0]["categories"] = ["obligation"]
    rows[0]["proposition_tier"] = "unknown"
    rows[0]["legal_effect_type"] = "unknown"
    rows[0]["is_compliance_relevant"] = True
    (ok_export / "propositions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    report = build_fresh_extraction_verification(ok_export)
    assert any(f.check_id == "categories_only_obligation_signal" for f in report.findings)


def test_write_artifacts(ok_export: Path) -> None:
    report = build_fresh_extraction_verification(ok_export)
    md_path, json_path = write_fresh_extraction_verification(ok_export, report)
    assert md_path.name == VERIFICATION_MD_FILENAME
    assert json_path.name == VERIFICATION_JSON_FILENAME
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["proposition_count"] == 4
    assert "Fresh extraction export verification" in md_path.read_text(encoding="utf-8")
