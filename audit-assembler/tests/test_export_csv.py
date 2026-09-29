"""Unit tests for Audit Assembler pairs CSV export."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from audit_assembler.export_csv import (
    CSV_HEADERS,
    MissingSummariesError,
    default_pairs_csv_path,
    export_csv,
    iter_pair_rows,
    load_presentation,
    try_write_pairs_csv,
    write_csv,
)

CATEGORY = "slurry"

PRESENTATION = {
    "categories": [{"id": "slurry", "title": "Slurry", "description": "Slurry."}],
    "pages": [
        {
            "content_id": "cid-a",
            "category": "slurry",
            "url": "https://www.gov.uk/a",
            "title": "Page A",
        }
    ],
    "legislation": [
        {
            "source_record_id": "lex-1",
            "category": "slurry",
            "name": "Act 1",
            "url": "https://www.legislation.gov.uk/uksi/2015/668/contents/made",
        }
    ],
    "legislation_propositions": [
        {
            "id": "prop:law1",
            "source_record_id": "lex-1",
            "proposition_text": "Law one.",
            "short_name": "L1",
            "label": "Law One",
            "fragment_locator": "regulation:4:paragraph:1",
            "provision_url": "https://www.legislation.gov.uk/uksi/2015/668/regulation/4/1",
        },
        {
            "id": "prop:law2",
            "source_record_id": "lex-1",
            "proposition_text": "Law two.",
            "short_name": None,
            "label": None,
            "fragment_locator": None,
            "provision_url": "https://www.legislation.gov.uk/uksi/2015/668",
        },
    ],
    "guidance_propositions": [
        {
            "id": "gp-multi",
            "content_id": "cid-a",
            "proposition_text": "Do Y.",
            "source_paragraphs": ["Para Y1", "Para Y2"],
            "section_locator": "section:y",
        },
        {
            "id": "gp-no-candidates",
            "content_id": "cid-a",
            "proposition_text": "Do none.",
            "source_paragraphs": ["Para none"],
            "section_locator": "section:none",
        },
        {
            "id": "gp-ungrounded",
            "content_id": "cid-a",
            "proposition_text": "Do Z.",
            "source_paragraphs": ["Para Z"],
            "section_locator": "section:z",
        },
        {
            "id": "gp-not-checked",
            "content_id": "cid-a",
            "proposition_text": "Do pending.",
            "source_paragraphs": [],
            "section_locator": None,
        },
    ],
    "guidance_proposition_match_summaries": [
        {
            "guidance_proposition_id": "gp-multi",
            "assessment_status": "COMPLETE",
            "coverage_result": "HAS_REPORTABLE_COMPARISON",
            "candidate_count": 2,
            "reportable_comparison_count": 2,
            "ungrounded_candidate_count": 0,
        },
        {
            "guidance_proposition_id": "gp-no-candidates",
            "assessment_status": "COMPLETE",
            "coverage_result": "NO_CANDIDATES_FOUND",
            "candidate_count": 0,
            "reportable_comparison_count": 0,
            "ungrounded_candidate_count": 0,
        },
        {
            "guidance_proposition_id": "gp-ungrounded",
            "assessment_status": "COMPLETE",
            "coverage_result": "ONLY_UNGROUNDED_CANDIDATES",
            "candidate_count": 1,
            "reportable_comparison_count": 0,
            "ungrounded_candidate_count": 1,
        },
        {
            "guidance_proposition_id": "gp-not-checked",
            "assessment_status": "NOT_CHECKED",
            "coverage_result": None,
            "candidate_count": None,
            "reportable_comparison_count": 0,
            "ungrounded_candidate_count": None,
        },
    ],
    "guidance_proposition_law_comparisons": [
        {
            "id": "m-1",
            "guidance_proposition_id": "gp-multi",
            "law_proposition_id": "prop:law1",
            "relationship": "CONFLICTS",
            "confidence": "high",
            "cosine_score": 0.8112,
            "bert_score_f1": None,
            "explanation": "conflicts with law1",
        },
        {
            "id": "m-2",
            "guidance_proposition_id": "gp-multi",
            "law_proposition_id": "prop:law2",
            "relationship": "GROUNDED",
            "confidence": "medium",
            "cosine_score": 0.7,
            "bert_score_f1": 0.55,
            "explanation": "grounded in law2",
        },
    ],
}


def _write_flat(dir_path: Path, presentation: dict) -> None:
    mapping = {
        "categories": "categories.json",
        "legislation": "legislation.json",
        "legislation_propositions": "legislation-propositions.json",
        "pages": "pages.json",
        "guidance_propositions": "guidance-propositions.json",
        "guidance_proposition_match_summaries": "guidance-proposition-match-summaries.json",
        "guidance_proposition_law_comparisons": "guidance-proposition-law-comparisons.json",
    }
    dir_path.mkdir(parents=True, exist_ok=True)
    for key, filename in mapping.items():
        (dir_path / filename).write_text(
            json.dumps(presentation[key], indent=2) + "\n", encoding="utf-8"
        )


def test_multi_pair_guidance_emits_one_row_per_comparison():
    rows = iter_pair_rows(PRESENTATION, CATEGORY)
    multi = [r for r in rows if r["guidance_proposition_id"] == "gp-multi"]
    assert len(multi) == 2
    assert {r["comparison_id"] for r in multi} == {"m-1", "m-2"}
    assert {r["relationship"] for r in multi} == {"CONFLICTS", "GROUNDED"}
    assert {r["law_proposition_id"] for r in multi} == {"prop:law1", "prop:law2"}
    assert all(r["guidance_proposition_text"] == "Do Y." for r in multi)
    assert all(r["source_paragraphs"] == "Para Y1 | Para Y2" for r in multi)
    law1 = next(r for r in multi if r["law_proposition_id"] == "prop:law1")
    assert law1["law_name"] == "Act 1"
    assert law1["law_url"] == (
        "https://www.legislation.gov.uk/uksi/2015/668/contents/made"
    )
    assert law1["law_provision_url"] == (
        "https://www.legislation.gov.uk/uksi/2015/668/regulation/4/1"
    )
    assert law1["law_short_name"] == "L1"
    assert law1["law_label"] == "Law One"
    assert law1["law_fragment_locator"] == "regulation:4:paragraph:1"
    assert law1["assessment_status"] == "COMPLETE"
    assert law1["coverage_result"] == "HAS_REPORTABLE_COMPARISON"


def test_no_candidates_stub_has_empty_law_columns():
    rows = iter_pair_rows(PRESENTATION, CATEGORY)
    stub = next(r for r in rows if r["guidance_proposition_id"] == "gp-no-candidates")
    assert stub["coverage_result"] == "NO_CANDIDATES_FOUND"
    assert stub["assessment_status"] == "COMPLETE"
    assert stub["comparison_id"] == ""
    assert stub["relationship"] == ""
    assert stub["law_proposition_id"] == ""
    assert stub["law_proposition_text"] == ""
    assert stub["law_name"] == ""
    assert stub["page_url"] == "https://www.gov.uk/a"
    assert stub["guidance_proposition_text"] == "Do none."


def test_only_ungrounded_candidates_emits_stub():
    rows = iter_pair_rows(PRESENTATION, CATEGORY)
    stub = next(r for r in rows if r["guidance_proposition_id"] == "gp-ungrounded")
    assert stub["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert stub["law_proposition_id"] == ""
    assert stub["relationship"] == ""


def test_not_checked_emits_stub_with_assessment():
    rows = iter_pair_rows(PRESENTATION, CATEGORY)
    stub = next(r for r in rows if r["guidance_proposition_id"] == "gp-not-checked")
    assert stub["assessment_status"] == "NOT_CHECKED"
    assert stub["coverage_result"] == ""
    assert stub["law_proposition_id"] == ""


def test_missing_summaries_raises():
    bare = {
        "guidance_propositions": PRESENTATION["guidance_propositions"],
        "legislation_propositions": PRESENTATION["legislation_propositions"],
        "pages": PRESENTATION["pages"],
        "legislation": PRESENTATION["legislation"],
        "guidance_proposition_match_summaries": [],
        "guidance_proposition_law_comparisons": [],
    }
    with pytest.raises(MissingSummariesError):
        iter_pair_rows(bare, CATEGORY)


def test_envelope_and_flat_dir_load_identical_rows(tmp_path: Path):
    flat = tmp_path / "flat"
    _write_flat(flat, PRESENTATION)
    envelope_path = tmp_path / "output.json"
    envelope_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "run_id": "test-run",
                "category": "slurry",
                "presentation": PRESENTATION,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    flat_pres, flat_cat = load_presentation(flat)
    env_pres, env_cat = load_presentation(envelope_path)
    assert env_cat == "slurry"
    assert flat_cat == "slurry"

    flat_rows = iter_pair_rows(flat_pres, flat_cat)
    env_rows = iter_pair_rows(env_pres, env_cat)
    assert flat_rows == env_rows
    assert len(flat_rows) == 5  # 2 pairs + 3 stubs


def test_write_csv_header_and_row_count(tmp_path: Path):
    rows = iter_pair_rows(PRESENTATION, CATEGORY)
    out = tmp_path / "pairs.csv"
    write_csv(rows, out)
    with out.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == CSV_HEADERS
        written = list(reader)
    assert len(written) == len(rows)
    assert written[0]["category"] == "slurry"


def test_export_csv_end_to_end(tmp_path: Path):
    envelope_path = tmp_path / "output.json"
    envelope_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "category": "slurry",
                "presentation": PRESENTATION,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "pairs.csv"
    warnings: list[str] = []
    rows = export_csv(envelope_path, out, warnings=warnings)
    assert out.is_file()
    assert len(rows) == 5
    assert warnings == []


def test_default_pairs_csv_path_next_to_envelope(tmp_path: Path):
    envelope = tmp_path / "output.json"
    envelope.write_text("{}", encoding="utf-8")
    assert default_pairs_csv_path(envelope) == tmp_path / "pairs.csv"


def test_default_pairs_csv_path_inside_flat_dir(tmp_path: Path):
    dest = tmp_path / "dest"
    dest.mkdir()
    assert default_pairs_csv_path(dest) == dest / "pairs.csv"


def test_try_write_pairs_csv_writes_same_rows_as_export_csv(tmp_path: Path):
    dest = tmp_path / "dest"
    _write_flat(dest, PRESENTATION)
    warnings: list[str] = []
    rows = try_write_pairs_csv(dest, warnings=warnings)
    assert rows is not None
    assert (dest / "pairs.csv").is_file()
    assert warnings == []
    with (dest / "pairs.csv").open(encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert [r["guidance_proposition_id"] for r in written] == [
        r["guidance_proposition_id"] for r in rows
    ]
    assert len(written) == 5


def test_try_write_pairs_csv_skips_when_summaries_missing(tmp_path: Path):
    dest = tmp_path / "legacy"
    _write_flat(
        dest,
        {
            **PRESENTATION,
            "guidance_proposition_match_summaries": [],
            "guidance_proposition_law_comparisons": [],
        },
    )
    warnings: list[str] = []
    rows = try_write_pairs_csv(dest, warnings=warnings)
    assert rows is None
    assert not (dest / "pairs.csv").exists()
    assert any("skipped pairs.csv" in w for w in warnings)


def test_export_csv_cli_defaults_out_next_to_envelope(tmp_path: Path):
    from typer.testing import CliRunner

    from audit_assembler.cli import app

    envelope_path = tmp_path / "output.json"
    envelope_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "category": "slurry",
                "presentation": PRESENTATION,
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["export-csv", "--input", str(envelope_path)])
    assert result.exit_code == 0, result.output
    out = tmp_path / "pairs.csv"
    assert out.is_file()
    with out.open(encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert written[0]["category"] == "slurry"
    assert len(written) == 5


def test_orphan_comparison_warns_and_skips():
    presentation = {
        **PRESENTATION,
        "guidance_proposition_law_comparisons": [
            *PRESENTATION["guidance_proposition_law_comparisons"],
            {
                "id": "m-orphan",
                "guidance_proposition_id": "gp-missing",
                "law_proposition_id": "prop:law1",
                "relationship": "GROUNDED",
                "confidence": None,
                "cosine_score": None,
                "bert_score_f1": None,
                "explanation": None,
            },
        ],
    }
    warnings: list[str] = []
    rows = iter_pair_rows(presentation, CATEGORY, warnings=warnings)
    assert all(r["comparison_id"] != "m-orphan" for r in rows)
    assert any("gp-missing" in w for w in warnings)
