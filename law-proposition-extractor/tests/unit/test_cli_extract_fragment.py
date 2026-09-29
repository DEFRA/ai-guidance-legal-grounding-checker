"""CLI: extract-fragment and eval-extract-fragment."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.extraction_prompt_eval import PROMPT_EVAL_JSON, PROMPT_EVAL_MD
from law_proposition_extractor_pipeline.extraction_workbench import FRAGMENT_TXT, PROPOSITIONS_NORMALISED_JSON

_REPO = Path(__file__).resolve().parents[2]
SLURRY = _REPO / "tests/fixtures/extraction_prompt_cases/slurry"
DRY_SMOKE = SLURRY / "_workbench_dry_smoke.json"
BOILERPLATE = SLURRY / "slurry-bad-diffuse-2018-reg-1-boilerplate.json"
EVAL_PASS_DIR = SLURRY / "eval_runs" / "diffuse-reg1-pass"

RUNNER = CliRunner()


def test_extract_fragment_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["extract-fragment", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "--eval" in result.stdout
    assert "--no-eval" in result.stdout
    assert "[/dry]" not in result.stdout


def test_extract_fragment_batch_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["extract-fragment-batch", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "--fixture-dir" in result.stdout
    assert "--output-root" in result.stdout
    assert "--fail-fast" in result.stdout


def test_extract_fragment_help_shows_eval_option() -> None:
    result = RUNNER.invoke(app, ["extract-fragment", "--help"])
    assert result.exit_code == 0
    assert "prompt_eval" in result.stdout.lower() or "eval" in result.stdout.lower()


def test_extract_fragment_rejects_eval_without_fixture(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "extract-fragment",
            "--case-or-run-dir",
            str(tmp_path),
            "--source-id",
            "x",
            "--locator",
            "regulation:1",
            "--output-dir",
            str(tmp_path / "out"),
            "--eval",
        ],
    )
    assert result.exit_code != 0
    assert "fixture" in (result.stdout + result.stderr).lower()


def test_extract_fragment_dry_with_eval_writes_outputs(tmp_path: Path) -> None:
    out = tmp_path / "dry-smoke"
    result = RUNNER.invoke(
        app,
        [
            "extract-fragment",
            "--fixture",
            str(DRY_SMOKE),
            "--mode",
            "dry",
            "--output-dir",
            str(out),
            "--eval",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / FRAGMENT_TXT).is_file()
    assert (out / PROPOSITIONS_NORMALISED_JSON).is_file()
    assert (out / PROMPT_EVAL_JSON).is_file()
    assert (out / PROMPT_EVAL_MD).is_file()
    payload = json.loads((out / PROMPT_EVAL_JSON).read_text(encoding="utf-8"))
    assert payload["case_id"] == "workbench-dry-smoke"


def test_eval_extract_fragment_standalone(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    shutil.copytree(EVAL_PASS_DIR, run_dir)
    result = RUNNER.invoke(
        app,
        [
            "eval-extract-fragment",
            "--fixture",
            str(BOILERPLATE),
            "--run-dir",
            str(run_dir),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (run_dir / PROMPT_EVAL_JSON).is_file()
    payload = json.loads((run_dir / PROMPT_EVAL_JSON).read_text(encoding="utf-8"))
    assert payload["passed"] is True
