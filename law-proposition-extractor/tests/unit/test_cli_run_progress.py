"""CLI progress helpers and quiet-mode behaviour."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.cli_progress import (
    NullPipelineProgress,
    null_pipeline_progress,
    pipeline_progress,
    print_completion_summary_table,
)
from law_proposition_extractor_pipeline.cli_run_summary import (
    build_cli_completion_summary,
    extraction_mode_from_bundle,
)
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary


def test_extraction_mode_reads_proposition_extraction_stage() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["stage_traces"] = [
        {"stage_name": "other", "inputs": {}},
        {"stage_name": "proposition extraction", "inputs": {"extraction_mode": "frontier"}},
    ]
    assert extraction_mode_from_bundle(bundle) == "frontier"


def test_build_cli_completion_summary_matches_demo_bundle() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["stage_traces"] = [
        {"stage_name": "proposition extraction", "inputs": {"extraction_mode": "heuristic"}}
    ]
    q = build_run_quality_summary(bundle)
    summary = build_cli_completion_summary(
        bundle, quality_summary=q, output_dir="/tmp/static-report"
    )
    assert summary["sources"] == len(bundle["source_records"])
    assert summary["propositions"] == len(bundle["propositions"])
    assert summary["extraction_mode"] == "heuristic"
    assert summary["output_directory"] == "/tmp/static-report"
    assert summary["run_quality_status"] == q["status"]


def test_null_pipeline_progress_singleton() -> None:
    assert null_pipeline_progress() is null_pipeline_progress()
    n = NullPipelineProgress()
    n.stage("x", detail="y")
    n.extraction_source(1, 2, "heuristic", "t")
    n.before_model_extract("local", 1, 2, "t")
    n.fallback_notice("s", "r")
    n.verbose("v")
    n.extraction_source_complete(SimpleNamespace())


@pytest.fixture
def example_case_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "demo" / "example_case.json"


def test_run_case_quiet_hides_summary_and_panel(example_case_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run-case", str(example_case_path), "--quiet"])
    assert result.exit_code == 0, result.stdout + result.stderr
    out = result.stdout + result.stderr
    assert "Run summary" not in out
    assert "Ran case:" not in out
    assert '"topic"' in out


def test_run_case_default_shows_run_summary_title(example_case_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run-case", str(example_case_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Run summary" in result.stdout


def test_pipeline_progress_quiet_yields_null() -> None:
    from rich.console import Console

    c = Console(record=True, width=120)
    with pipeline_progress(c, quiet=True, verbose=False) as pr:
        assert pr is null_pipeline_progress()


def test_print_completion_summary_hides_derived_cache_dir_by_default() -> None:
    from rich.console import Console

    c = Console(record=True, width=120)
    print_completion_summary_table(
        c,
        {
            "sources": 1,
            "propositions": 2,
            "extraction_mode": "local",
            "extraction_mode_requested": "local",
            "extraction_mode_effective": "local",
            "fallback_count": 0,
            "low_confidence_count": 0,
            "validation_warning_count": 0,
            "output_directory": "dist/static-report",
            "derived_cache_dir": "/var/folders/xx/T/law-proposition-extractor/derived-artifacts",
            "run_quality_status": "pass",
        },
    )
    out = c.export_text()
    assert "Derived cache directory" not in out
    assert "/var/folders" not in out


def test_print_completion_summary_shows_derived_cache_dir_when_verbose() -> None:
    from rich.console import Console

    cache = "/tmp/lpe-derived"
    c = Console(record=True, width=120)
    print_completion_summary_table(
        c,
        {
            "sources": 1,
            "propositions": 2,
            "extraction_mode": "local",
            "extraction_mode_requested": "local",
            "extraction_mode_effective": "local",
            "fallback_count": 0,
            "low_confidence_count": 0,
            "validation_warning_count": 0,
            "output_directory": "",
            "derived_cache_dir": cache,
            "run_quality_status": "pass",
        },
        verbose=True,
    )
    out = c.export_text()
    assert "Derived cache directory" in out
    assert cache in out


def test_pipeline_progress_rich_supports_extraction_completion_hook() -> None:
    from rich.console import Console

    c = Console(record=True, width=120)
    with pipeline_progress(c, quiet=False, verbose=False) as pr:
        pr.before_model_extract(
            "frontier",
            1,
            1,
            "Test source",
            source_record_id="src-001",
            estimated_input_tokens=1234,
            extraction_llm_chunk_index=1,
            extraction_llm_chunk_total=1,
            trace={"source_record_id": "src-001"},
        )
        pr.extraction_source_complete(
            SimpleNamespace(
                propositions=[{"id": "p1"}, {"id": "p2"}],
                fallback_used=True,
                failed_closed=False,
                extraction_llm_call_traces=[
                    {"source_record_id": "src-001", "skip_reason": "context_window_risk"}
                ],
            )
        )
