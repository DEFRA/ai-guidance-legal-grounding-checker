"""CLI ergonomics and Law Discovery Law Proposition Extractor intake bundle commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app, run_case_command
from law_proposition_extractor_pipeline.source_bundle_intake import (
    FullLawDiscoveryBundleRejectedError,
    IntakeBundleSelection,
    load_source_bundle,
    plan_intake_bundle_dry_run,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def _intake_bundle_fixture() -> dict:
    return {
        "bundle_id": "bundle-cli-test",
        "category_id": "cli_test_category",
        "created_at": "2026-06-01T00:00:00Z",
        "principal_sources": [
            {
                "source_id": "lex-cli-1",
                "title": "Test Instrument One",
                "citation": None,
                "source_type": "uksi",
                "canonical_uri": "http://www.legislation.gov.uk/id/uksi/2020/1",
                "source_system": "lex",
                "jurisdiction_extent": ["England"],
                "relationship_to_category": "directly_regulates",
                "review_status": "accepted",
            },
            {
                "source_id": "lex-cli-2",
                "title": "Test Instrument Two",
                "citation": None,
                "source_type": "uksi",
                "canonical_uri": "http://www.legislation.gov.uk/id/uksi/2020/2",
                "source_system": "lex",
                "jurisdiction_extent": ["England"],
                "relationship_to_category": "directly_regulates",
                "review_status": "accepted",
            },
        ],
        "amending_sources": [],
        "revocation_sources": [],
        "contextual_sources": [],
        "rejected_sources": [],
        "relationships": [],
        "metadata": {
            "intake": {
                "kind": "judit_intake",
                "filter_policy": {
                    "principal_only": True,
                    "max_principal_sources": 2,
                    "priority_policy": "current_core",
                    "exclude_jurisdictions": ["Northern Ireland"],
                },
            },
        },
    }


def test_run_case_help_exits_zero_and_documents_case_path() -> None:
    result = RUNNER.invoke(app, ["run-case", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "CASE_PATH" in result.stdout
    assert "run-bundle" in result.stdout or "source bundle" in result.stdout.lower()


def test_top_level_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "run-case" in result.stdout
    assert "run-bundle" in result.stdout


def test_run_bundle_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["run-bundle", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "SOURCE_BUNDLE_JSON" in result.stdout or "source_bundle" in result.stdout.lower()
    assert "--output" in result.stdout
    assert "--dry-run" in result.stdout
    assert "progress-every" in result.stdout or "--progress-eve" in result.stdout
    assert "--very-verbose" in result.stdout


def test_export_case_help_documents_output_dir_and_output_alias() -> None:
    result = RUNNER.invoke(app, ["export-case", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "--output-dir" in result.stdout
    assert "--output" in result.stdout


def test_export_case_output_alias_passes_output_dir(tmp_path: Path) -> None:
    case_path = _REPO_ROOT / "data/demo/example_case.json"
    if not case_path.is_file():
        pytest.skip("example_case.json missing")
    out_dir = tmp_path / "export-out"
    with patch("law_proposition_extractor_pipeline.cli.export_case_file") as export_mock:
        export_mock.return_value = {
            "divergence_assessments": [],
            "run_quality_summary": {},
        }
        result = RUNNER.invoke(
            app,
            [
                "export-case",
                str(case_path),
                "--output",
                str(out_dir),
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    export_mock.assert_called_once()
    assert export_mock.call_args.kwargs["output_dir"] == str(out_dir)


def test_run_case_missing_case_path_errors_without_help() -> None:
    result = RUNNER.invoke(app, ["run-case"])
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "CASE_PATH" in combined or "Missing argument" in combined


def test_run_bundle_dry_run_prints_summary_and_titles(tmp_path: Path) -> None:
    bundle_path = tmp_path / "intake.json"
    bundle_path.write_text(
        __import__("json").dumps(_intake_bundle_fixture()),
        encoding="utf-8",
    )
    out_dir = tmp_path / "case-out"
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        result = RUNNER.invoke(
            app,
            [
                "run-bundle",
                str(bundle_path),
                "--output",
                str(out_dir),
                "--dry-run",
            ],
        )
    run_mock.assert_not_called()
    assert result.exit_code == 0, result.stdout + result.stderr
    out = result.stdout
    assert "cli_test_category" in out
    assert "principal_sources: 2" in out
    assert "intake.kind: judit_intake" in out
    assert "Test Instrument One" in out
    assert "Test Instrument Two" in out
    assert "case-out" in out
    assert "Intended case output" in out
    assert "Dry run" in out
    assert not (out_dir / "case.json").exists()


def test_run_bundle_progress_options_reach_run_and_progress_config(tmp_path: Path) -> None:
    bundle_path = tmp_path / "intake.json"
    bundle_path.write_text(
        __import__("json").dumps(_intake_bundle_fixture()),
        encoding="utf-8",
    )
    out_dir = tmp_path / "case-out"
    progress_cm = MagicMock()
    progress_cm.__enter__.return_value = MagicMock()
    progress_cm.__exit__.return_value = False
    with (
        patch("law_proposition_extractor_pipeline.cli.pipeline_progress", return_value=progress_cm) as progress_mock,
        patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock,
    ):
        run_mock.return_value = {"topic": {}, "source_records": [], "propositions": []}
        result = RUNNER.invoke(
            app,
            [
                "run-bundle",
                str(bundle_path),
                "--output",
                str(out_dir),
                "--quiet",
                "--progress-every",
                "5",
                "--very-verbose",
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    progress_mock.assert_called_once()
    assert progress_mock.call_args.kwargs["very_verbose"] is True
    assert progress_mock.call_args.kwargs["progress_every"] == 5
    run_mock.assert_called_once()
    assert run_mock.call_args.kwargs["progress_every"] == 5


def test_run_bundle_judit_intake_writes_case_and_can_run(tmp_path: Path) -> None:
    bundle_path = tmp_path / "intake.json"
    bundle_path.write_text(
        __import__("json").dumps(_intake_bundle_fixture()),
        encoding="utf-8",
    )
    out_dir = tmp_path / "case-out"
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        run_mock.return_value = {"topic": {}, "source_records": [], "propositions": []}
        result = RUNNER.invoke(
            app,
            [
                "run-bundle",
                str(bundle_path),
                "--output",
                str(out_dir),
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    case_json = out_dir / "case.json"
    assert case_json.is_file()
    run_mock.assert_called_once()
    assert str(case_json) in str(run_mock.call_args.kwargs.get("case_path") or run_mock.call_args[0][0])


def test_run_bundle_refuses_full_ada_reviewed_bundle(tmp_path: Path) -> None:
    path = _REPO_ROOT / "source-bundle-reviewed.json"
    if not path.is_file():
        pytest.skip("repo reviewed fixture missing")
    result = RUNNER.invoke(
        app,
        [
            "run-bundle",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "Full reviewed Law Discovery bundle" in result.stdout + result.stderr


def test_run_bundle_allows_full_ada_with_flag_dry_run(tmp_path: Path) -> None:
    path = _REPO_ROOT / "source-bundle-reviewed.json"
    if not path.is_file():
        pytest.skip("repo reviewed fixture missing")
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        result = RUNNER.invoke(
            app,
            [
                "run-bundle",
                str(path),
                "--output",
                str(tmp_path / "out"),
                "--allow-full-law-discovery-bundle",
                "--dry-run",
            ],
        )
    run_mock.assert_not_called()
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "principal_sources:" in result.stdout


def test_repo_judit_intake_fixture_dry_run() -> None:
    path = _REPO_ROOT / "source-bundle-law-proposition-extractor-intake-principal-only.json"
    if not path.is_file():
        pytest.skip("repo intake fixture missing")
    bundle = load_source_bundle(path)
    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())
    assert plan.intake_kind == "judit_intake"
    assert plan.selected_source_count == 10


def test_run_case_command_is_not_hardcoded_to_run_case_only() -> None:
    """Entry point must forward argv so ``run-case --help`` works."""
    import sys

    with patch.object(sys, "argv", ["law-proposition-extractor-run-case", "run-case", "--help"]):
        with patch("law_proposition_extractor_pipeline.cli.app") as app_mock:
            run_case_command()
    app_mock.assert_called_once()
    assert app_mock.call_args.kwargs.get("prog_name") == "law-proposition-extractor-run-case"
