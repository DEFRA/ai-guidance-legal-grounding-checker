"""Unit tests for regulation paragraph fragmentation verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.regulation_paragraph_fragmentation_verification import (
    EXPECTED_REGULATION_36_LOCATORS,
    build_report_from_export,
    build_report_from_fixture_xml,
    verification_exit_code,
    write_verification_outputs,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "regulation_paragraph_fragmentation"
)
WSI_FIXTURE = FIXTURE_ROOT / "wsi_2021_77_regulation_36.xml"
WSI_LIVE_CLML_FIXTURE = FIXTURE_ROOT / "wsi_2021_77_regulation_36_live_clml.xml"


def test_fixture_verification_passes_for_regulation_36_paragraphs() -> None:
    report = build_report_from_fixture_xml(WSI_FIXTURE)
    assert report.passed is True
    assert report.matching_locators == list(EXPECTED_REGULATION_36_LOCATORS)
    assert report.missing_locators == []
    assert verification_exit_code(report) == 0
    by_locator = {row.locator: row for row in report.fragment_rows}
    assert by_locator["regulation:36:paragraph:4"].parent_fragment_id is not None
    assert "occupier must make a record" in by_locator["regulation:36:paragraph:4"].text_preview


def test_live_clml_fixture_verification_passes_for_regulation_36_paragraphs() -> None:
    report = build_report_from_fixture_xml(WSI_LIVE_CLML_FIXTURE)
    assert report.passed is True
    assert report.matching_locators == list(EXPECTED_REGULATION_36_LOCATORS)
    by_locator = {row.locator: row for row in report.fragment_rows}
    assert by_locator["regulation:36"].text_length > 50
    assert by_locator["regulation:36"].text_preview.startswith("36.")
    assert "occupier must make a record" in by_locator["regulation:36:paragraph:4"].text_preview
    assert by_locator["regulation:36:paragraph:4"].text_preview.startswith(
        "(4) The occupier must make a record"
    )


def test_export_verification_fails_when_paragraph_children_missing(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "source_fragments.json").write_text(
        json.dumps(
            [
                {
                    "id": "frag-reg-36",
                    "source_record_id": "lex-805b03f284dcf364",
                    "locator": "regulation:36",
                    "fragment_text": "Whole regulation 36 body.",
                }
            ]
        ),
        encoding="utf-8",
    )
    report = build_report_from_export(export_dir)
    assert report.passed is False
    assert report.matching_locators == ["regulation:36"]
    assert report.missing_locators == [
        "regulation:36:paragraph:1",
        "regulation:36:paragraph:2",
        "regulation:36:paragraph:3",
        "regulation:36:paragraph:4",
    ]
    assert verification_exit_code(report) == 1


def test_export_verification_passes_when_paragraph_children_present(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    fragments = [
        {
            "id": "frag-reg-36",
            "source_record_id": "lex-805b03f284dcf364",
            "locator": locator,
            "fragment_text": f"Body for {locator}.",
            "parent_fragment_id": "frag-reg-36" if locator != "regulation:36" else None,
        }
        for locator in EXPECTED_REGULATION_36_LOCATORS
    ]
    (export_dir / "source_fragments.json").write_text(json.dumps(fragments), encoding="utf-8")
    report = build_report_from_export(export_dir)
    assert report.passed is True
    assert verification_exit_code(report) == 0


def test_write_verification_outputs(tmp_path: Path) -> None:
    report = build_report_from_fixture_xml(WSI_FIXTURE)
    md_path, json_path = write_verification_outputs(tmp_path / "out", report)
    assert md_path.is_file()
    assert json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["matching_locators"] == list(EXPECTED_REGULATION_36_LOCATORS)


@pytest.mark.parametrize("fixture_path", [WSI_FIXTURE])
def test_fixture_file_exists(fixture_path: Path) -> None:
    assert fixture_path.is_file()
