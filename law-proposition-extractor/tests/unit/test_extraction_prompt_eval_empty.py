"""Evaluator and workbench behaviour when extraction output is empty."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.extraction_prompt_eval import (
    PROMPT_EVAL_JSON,
    evaluate_prompt_lab_extraction,
    load_actual_propositions_with_meta,
)
from law_proposition_extractor_pipeline.extraction_workbench import (
    EXTRACTION_TRACE_JSON,
    PROPOSITIONS_NORMALISED_JSON,
    PROPOSITIONS_RAW_JSON,
    REVIEW_MD,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)

SLURRY = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
BOILERPLATE = SLURRY / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"
DRY_SMOKE = SLURRY / "_workbench_dry_smoke.json"
EVAL_RUNS = SLURRY / "eval_runs"
RUNNER = CliRunner()


def test_eval_empty_actual_rows_fails_without_crash() -> None:
    empty_dir = EVAL_RUNS / "empty-actuals"
    result = evaluate_prompt_lab_extraction(fixture=BOILERPLATE, run_dir=empty_dir)
    assert result.eval_status == "fail"
    assert result.passed is False
    assert result.actual_count == 0
    assert result.expected_count == 4
    assert result.matched_expected_count == 0
    assert len(result.expected_matches) == 4
    assert all(not m.matched for m in result.expected_matches)
    assert result.checks["no_actual_propositions"]["passed"] is False
    assert all(
        m.suggested_failure_reason == "no_actual_propositions" for m in result.expected_matches
    )


def test_load_falls_back_to_raw_when_normalised_invalid(tmp_path: Path) -> None:
    (tmp_path / PROPOSITIONS_NORMALISED_JSON).write_text("{not json", encoding="utf-8")
    (tmp_path / PROPOSITIONS_RAW_JSON).write_text(
        json.dumps([{"id": "p1", "proposition_text": "x", "legal_effect_type": "obligation"}]),
        encoding="utf-8",
    )
    loaded = load_actual_propositions_with_meta(tmp_path, prefer_normalised=True)
    assert len(loaded.rows) == 1
    assert loaded.source_file == PROPOSITIONS_RAW_JSON
    assert any("fell back" in w for w in loaded.warnings)


def test_workbench_empty_parsed_rows_status(tmp_path: Path) -> None:
    result = run_extract_fragment_workbench(
        fixture_path=DRY_SMOKE,
        extraction_mode="dry",
        dry_raw_model_output='{"propositions": []}',
    )
    assert result.workbench_status == "empty_extraction"
    assert "no_parsed_extraction_rows" in result.empty_reasons
    assert result.actual_proposition_count == 0
    out = write_extract_fragment_workbench_outputs(result, tmp_path / "empty-parsed")
    trace = json.loads((out / EXTRACTION_TRACE_JSON).read_text(encoding="utf-8"))
    assert trace["status"] == "empty_extraction"
    review = (out / REVIEW_MD).read_text(encoding="utf-8")
    assert "empty_extraction" in review
    assert "no_parsed_extraction_rows" in review


def test_workbench_empty_raw_output_status(tmp_path: Path) -> None:
    result = run_extract_fragment_workbench(
        fixture_path=DRY_SMOKE,
        extraction_mode="dry",
        dry_raw_model_output="",
    )
    assert result.workbench_status in {"empty_extraction", "failed"}
    assert "empty_raw_model_output" in result.empty_reasons


def test_cli_extract_fragment_dry_eval_empty_actual_writes_eval_artifacts(tmp_path: Path) -> None:
    empty_fixture = tmp_path / "empty-dry.json"
    empty_fixture.write_text(
        json.dumps(
            {
                **json.loads(DRY_SMOKE.read_text(encoding="utf-8")),
                "dry": {"raw_model_output": '{"propositions": []}'},
                "expected_propositions": [],
                "evaluation": {"strict_proposition_count": True},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "dry-empty-eval"
    result = RUNNER.invoke(
        app,
        [
            "extract-fragment",
            "--fixture",
            str(empty_fixture),
            "--mode",
            "dry",
            "--output-dir",
            str(out),
            "--eval",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / PROMPT_EVAL_JSON).is_file()


def test_eval_extract_fragment_on_baseline_run_no_crash() -> None:
    baseline = Path("runs/prompt-lab/baseline-bad-diffuse-2018-reg-1")
    if not baseline.is_dir():
        pytest.skip("baseline run dir not present")
    result = evaluate_prompt_lab_extraction(fixture=BOILERPLATE, run_dir=baseline)
    assert result.eval_status in {"pass", "fail"}
    if result.actual_count == 0:
        assert result.eval_status == "fail"
        assert result.checks["no_actual_propositions"]["passed"] is False
    else:
        assert result.actual_count == 4
        assert result.eval_status == "pass"
