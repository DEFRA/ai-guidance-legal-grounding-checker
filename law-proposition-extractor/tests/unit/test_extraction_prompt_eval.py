"""Prompt-lab extraction evaluation (saved run fixtures, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_prompt_eval import (
    PROMPT_EVAL_JSON,
    PROMPT_EVAL_MD,
    evaluate_prompt_lab_extraction,
    write_prompt_eval_outputs,
)

SLURRY = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
FIXTURE = SLURRY / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"
EVAL_RUNS = SLURRY / "eval_runs"


def test_eval_pass_run_matches_all_expected(tmp_path: Path) -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=FIXTURE,
        run_dir=EVAL_RUNS / "diffuse-reg1-pass",
    )
    assert result.passed is True
    assert result.matched_expected_count == 4
    assert result.actual_count == 4
    assert not result.extra_actual
    assert not result.missing_effects


def test_eval_fail_compressed_single_proposition() -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=FIXTURE,
        run_dir=EVAL_RUNS / "diffuse-reg1-fail-compressed",
    )
    assert result.passed is False
    assert result.checks["proposition_count"]["passed"] is False
    assert result.checks["over_compression"]["passed"] is False
    assert result.matched_expected_count < 4


def test_eval_fail_boilerplate_marked_checkable() -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=FIXTURE,
        run_dir=EVAL_RUNS / "diffuse-reg1-fail-boilerplate-checkable",
    )
    assert result.passed is False
    assert result.checks["boilerplate_classification"]["passed"] is False
    assert result.checks["checkable_count"]["passed"] is False


def test_write_prompt_eval_outputs(tmp_path: Path) -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=FIXTURE,
        run_dir=EVAL_RUNS / "diffuse-reg1-pass",
    )
    json_path, md_path = write_prompt_eval_outputs(result, tmp_path)
    assert json_path == tmp_path / PROMPT_EVAL_JSON
    assert md_path == tmp_path / PROMPT_EVAL_MD
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["case_id"] == "slurry-bad-diffuse-2018-reg-1-boilerplate"
    assert "expected_matches" in payload
    md = md_path.read_text(encoding="utf-8")
    assert "PASS" in md or "FAIL" in md
    assert "Expected proposition matches" in md


def test_expected_match_reports_failure_reason() -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=FIXTURE,
        run_dir=EVAL_RUNS / "diffuse-reg1-fail-compressed",
    )
    unmatched = [m for m in result.expected_matches if not m.matched]
    assert unmatched
    assert unmatched[0].suggested_failure_reason
