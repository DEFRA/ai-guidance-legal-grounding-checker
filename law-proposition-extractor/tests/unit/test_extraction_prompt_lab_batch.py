"""Batch runner for extraction prompt-lab fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.extraction_prompt_lab_batch import (
    PROMPT_LAB_SUMMARY_JSON,
    PROMPT_LAB_SUMMARY_MD,
    PromptLabBatchRow,
    compute_batch_verdict,
    discover_prompt_lab_fixtures,
    run_prompt_lab_batch,
)

_REPO = Path(__file__).resolve().parents[2]
SLURRY = _REPO / "tests/fixtures/extraction_prompt_cases/slurry"
DRY_SMOKE = SLURRY / "_workbench_dry_smoke.json"
BOILERPLATE = SLURRY / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"
RUNNER = CliRunner()


def _row(**overrides: object) -> PromptLabBatchRow:
    base = {
        "fixture_file": "/tmp/x.json",
        "case_id": "x",
        "tier": "good",
        "label": "GOOD — test",
        "evaluation_mode": "exhaustive",
        "status": "fail",
        "expected_proposition_count": 1,
        "actual_proposition_count": 5,
        "matched_expected": "1/1",
        "extra_actual_count": 4,
        "evidence_failures": 0,
        "failure_themes": ["fixture_or_eval_policy_warning"],
    }
    base.update(overrides)
    return PromptLabBatchRow(**base)  # type: ignore[arg-type]


def test_compute_batch_verdict_fixture_policy_when_most_extras_only() -> None:
    rows = [
        _row(case_id="extras-a"),
        _row(case_id="extras-b"),
        _row(
            case_id="substantive",
            matched_expected="5/8",
            extra_actual_count=3,
            evidence_failures=2,
            failure_themes=["missing_evidence_quote", "weak_subject_or_action"],
        ),
        _row(
            case_id="classifier",
            matched_expected="0/2",
            expected_proposition_count=2,
            actual_proposition_count=8,
            extra_actual_count=8,
            failure_themes=["missing_expected_legal_effect"],
        ),
    ]
    verdict, detail = compute_batch_verdict(rows)
    assert verdict == "fixture_policy_review_needed"
    assert "extras-a" not in detail or "2 of 4" in detail or "matched all expected" in detail


def test_compute_batch_verdict_prompt_change_when_no_extras_dominance() -> None:
    rows = [
        _row(
            case_id="only-substantive",
            matched_expected="0/2",
            expected_proposition_count=2,
            actual_proposition_count=0,
            extra_actual_count=0,
            evidence_failures=2,
            failure_themes=["missing_evidence_quote"],
        ),
    ]
    verdict, _ = compute_batch_verdict(rows)
    assert verdict == "failures_suggest_prompt_change"


def test_discover_skips_helper_and_eval_runs() -> None:
    paths = discover_prompt_lab_fixtures(SLURRY)
    names = {p.name for p in paths}
    assert "_workbench_dry_smoke.json" not in names
    assert not any("eval_runs" in str(p) for p in paths)
    assert "slurry-good-simple-prohibition-spread-buffer.json" in names


def test_discover_limit_and_glob() -> None:
    paths = discover_prompt_lab_fixtures(
        SLURRY,
        fixture_glob="slurry-good-*.json",
        limit=2,
    )
    assert len(paths) == 2
    assert all(p.name.startswith("slurry-good-") for p in paths)


def test_dry_batch_writes_summary(tmp_path: Path) -> None:
    out = tmp_path / "batch-dry"
    result = run_prompt_lab_batch(
        output_root=out,
        extraction_mode="dry",
        fixture_paths=[DRY_SMOKE],
        run_eval=True,
    )
    assert len(result.rows) == 1
    assert result.rows[0].status in {"pass", "warn", "fail"}
    assert (out / PROMPT_LAB_SUMMARY_JSON).is_file()
    assert (out / PROMPT_LAB_SUMMARY_MD).is_file()
    payload = json.loads((out / PROMPT_LAB_SUMMARY_JSON).read_text(encoding="utf-8"))
    assert payload["verdict"]
    assert payload["rows"][0]["case_id"] == "workbench-dry-smoke"


def test_batch_continues_after_fixture_failure(tmp_path: Path) -> None:
    good = tmp_path / "good-dry.json"
    shutil.copy(DRY_SMOKE, good)
    bad = tmp_path / "bad-no-dry.json"
    shutil.copy(BOILERPLATE, bad)
    out = tmp_path / "batch-mixed"
    result = run_prompt_lab_batch(
        output_root=out,
        extraction_mode="dry",
        fixture_paths=[bad, good],
        run_eval=True,
        fail_fast=False,
    )
    assert len(result.rows) == 2
    statuses = {row.fixture_file: row.status for row in result.rows}
    assert statuses[str(bad.resolve())] == "skipped"
    assert statuses[str(good.resolve())] in {"pass", "warn", "fail"}


def test_batch_fail_fast_stops_after_first_failure(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    good = tmp_path / "good-dry.json"
    shutil.copy(DRY_SMOKE, good)
    out = tmp_path / "batch-fast"
    result = run_prompt_lab_batch(
        output_root=out,
        extraction_mode="dry",
        fixture_paths=[broken, good],
        run_eval=True,
        fail_fast=True,
    )
    assert len(result.rows) == 1
    assert result.rows[0].status == "error"


def test_cli_extract_fragment_batch_dry_smoke(tmp_path: Path) -> None:
    out = tmp_path / "cli-batch"
    result = RUNNER.invoke(
        app,
        [
            "extract-fragment-batch",
            "--fixture",
            str(DRY_SMOKE),
            "--mode",
            "dry",
            "--output-root",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / PROMPT_LAB_SUMMARY_JSON).is_file()
    assert (out / PROMPT_LAB_SUMMARY_MD).is_file()


def test_cli_rejects_invalid_fixture_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    result = RUNNER.invoke(
        app,
        [
            "extract-fragment-batch",
            "--fixture",
            str(missing),
            "--mode",
            "dry",
            "--output-root",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
    assert "not found" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize("helper_name", ["_helper.json"])
def test_discover_never_includes_underscore_fixtures(tmp_path: Path, helper_name: str) -> None:
    helper = tmp_path / helper_name
    helper.write_text("{}", encoding="utf-8")
    real = tmp_path / "slurry-good-test.json"
    real.write_text(
        json.dumps(
            {
                "case_id": "x",
                "label": "GOOD — test",
                "source_title": "T",
                "source_record_id": "s",
                "fragment_locator": "regulation:1",
                "fragment_text": "text",
                "why_this_case": "test",
                "expected_challenges": [],
                "expected_propositions": [],
            }
        ),
        encoding="utf-8",
    )
    paths = discover_prompt_lab_fixtures(tmp_path)
    assert helper not in paths
    assert real.resolve() in paths
