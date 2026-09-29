"""Evaluation modes for prompt-lab fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.extraction_prompt_eval import (
    _check_extra_actual,
    _check_proposition_count,
    evaluate_prompt_lab_extraction,
)

SLURRY = Path(__file__).resolve().parents[1] / "fixtures" / "extraction_prompt_cases" / "slurry"
GOOD_PROHIBITION = SLURRY / "slurry-good-simple-prohibition-spread-buffer.json"
UNLESS_EXCEPT = SLURRY / "slurry-bad-unless-except-organic-manure-250kg.json"
LIVESTOCK_TABLE = SLURRY / "slurry-ugly-schedule-livestock-manure-table.json"
BOILERPLATE = SLURRY / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"
EVAL_RUNS = SLURRY / "eval_runs"

BASELINE_GOOD = Path("runs/prompt-lab/baseline-good-prohibition")
BASELINE_UNLESS = Path("runs/prompt-lab/baseline-bad-unless-except")
BASELINE_TABLE = Path("runs/prompt-lab/baseline-ugly-livestock-table")
BASELINE_FRONTIER = Path("runs/prompt-lab/baseline-frontier")

PROMPT39_MODE_FIXTURES: list[tuple[Path, str]] = [
    (SLURRY / "slurry-bad-over-compressed-crop-nitrogen-table.json", "minimum"),
    (SLURRY / "slurry-good-definition-slurry-sssaho-2010.json", "targeted"),
    (SLURRY / "slurry-good-simple-obligation-170kg-n.json", "targeted"),
    (SLURRY / "slurry-ugly-appeal-nvz-designation-reg-6.json", "minimum"),
    (SLURRY / "slurry-ugly-cross-reference-derogation-directive.json", "minimum"),
    (SLURRY / "slurry-ugly-transitional-nvz-wales-reg-2.json", "minimum"),
]


def test_targeted_mode_allows_extras() -> None:
    count = _check_proposition_count(
        actual_count=8,
        expected_count=1,
        mode="targeted",
        strict=False,
        max_extra_actual=None,
    )
    assert count["passed"] is True
    extra = _check_extra_actual(
        extra_count=7,
        mode="targeted",
        allow_extra_actual=True,
        max_extra_actual=None,
    )
    assert extra["passed"] is True
    assert extra["status"] == "extras_allowed"


def test_exhaustive_mode_flags_extras() -> None:
    extra = _check_extra_actual(
        extra_count=1,
        mode="exhaustive",
        allow_extra_actual=False,
        max_extra_actual=None,
    )
    assert extra["passed"] is False
    assert extra["status"] == "unexpected_extras"


def test_minimum_mode_requires_matches_but_allows_extras() -> None:
    count = _check_proposition_count(
        actual_count=8,
        expected_count=8,
        mode="minimum",
        strict=False,
        max_extra_actual=None,
    )
    assert count["passed"] is True
    extra = _check_extra_actual(
        extra_count=2,
        mode="minimum",
        allow_extra_actual=True,
        max_extra_actual=None,
    )
    assert extra["passed"] is True


def test_table_rows_mode_allows_extra_table_rows() -> None:
    extra = _check_extra_actual(
        extra_count=4,
        mode="table_rows",
        allow_extra_actual=True,
        max_extra_actual=None,
    )
    assert extra["passed"] is True
    assert "table_rows" in str(extra["detail"])


@pytest.mark.parametrize(
    ("fixture", "run_dir"),
    [
        (GOOD_PROHIBITION, BASELINE_GOOD),
        (UNLESS_EXCEPT, BASELINE_UNLESS),
        (LIVESTOCK_TABLE, BASELINE_TABLE),
    ],
)
def test_updated_slurry_fixtures_pass_against_baseline_runs(
    fixture: Path,
    run_dir: Path,
) -> None:
    if not run_dir.is_dir():
        pytest.skip(f"baseline run dir not present: {run_dir}")
    result = evaluate_prompt_lab_extraction(fixture=fixture, run_dir=run_dir)
    assert result.checks["evaluation_mode"]["mode"] == json.loads(
        fixture.read_text(encoding="utf-8")
    )["evaluation"]["mode"]
    assert result.passed is True, result.summary
    assert result.matched_expected_count == result.expected_count


def test_good_prohibition_targeted_passes_with_extra_rows() -> None:
    if not BASELINE_GOOD.is_dir():
        pytest.skip("baseline good-prohibition run dir not present")
    result = evaluate_prompt_lab_extraction(fixture=GOOD_PROHIBITION, run_dir=BASELINE_GOOD)
    assert result.passed is True
    assert result.matched_expected_count == 1
    assert result.actual_count == 8
    assert len(result.extra_actual) == 7
    assert result.summary["allow_extra_actual"] is True


def test_livestock_table_passes_or_warns_only() -> None:
    if not BASELINE_TABLE.is_dir():
        pytest.skip("baseline livestock-table run dir not present")
    result = evaluate_prompt_lab_extraction(fixture=LIVESTOCK_TABLE, run_dir=BASELINE_TABLE)
    assert result.passed is True
    assert result.matched_expected_count == 4
    assert result.checks["evaluation_mode"]["mode"] == "table_rows"
    if result.extra_actual:
        assert result.checks["extra_actual"]["passed"] is True


def test_exhaustive_boilerplate_still_passes_eval_run() -> None:
    result = evaluate_prompt_lab_extraction(
        fixture=BOILERPLATE,
        run_dir=EVAL_RUNS / "diffuse-reg1-pass",
    )
    assert result.passed is True
    assert result.checks["evaluation_mode"]["mode"] == "exhaustive"


@pytest.mark.parametrize(("fixture", "expected_mode"), PROMPT39_MODE_FIXTURES)
def test_prompt39_fixture_modes_pass_against_baseline_frontier(
    fixture: Path,
    expected_mode: str,
) -> None:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    run_dir = BASELINE_FRONTIER / str(data["case_id"])
    if not run_dir.is_dir():
        pytest.skip(f"baseline-frontier run dir not present: {run_dir}")
    result = evaluate_prompt_lab_extraction(fixture=fixture, run_dir=run_dir)
    assert result.checks["evaluation_mode"]["mode"] == expected_mode
    assert result.checks["evaluation_mode"]["mode"] == data["evaluation"]["mode"]
    assert result.passed is True, result.summary
    assert result.matched_expected_count == result.expected_count
