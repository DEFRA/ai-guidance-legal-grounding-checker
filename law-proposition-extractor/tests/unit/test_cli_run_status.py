"""CLI run-status command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.run_persistence import build_persisted_run_config, persist_run_outputs
from law_proposition_extractor_pipeline.run_status import build_run_status_report, suggest_next_command

_REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def _local_llm_bundle(*, proposition_count: int = 3, cached_failed: int = 0) -> dict:
    props = [
        {
            "id": f"prop-{idx}",
            "topic_id": "topic-1",
            "cluster_id": "cluster-1",
            "source_record_id": "src-1",
            "text": f"Proposition {idx}",
            "display_label": f"P{idx}",
            "metadata": {},
        }
        for idx in range(proposition_count)
    ]
    traces = [{"llm_invoked": True, "llm_call_succeeded": True} for _ in range(2)]
    if cached_failed:
        traces.extend(
            [{"llm_cache_hit": "failed_chunk_cached", "skip_reason": "failed_chunk_cached"}]
            * cached_failed
        )
    return {
        "workflow_mode": "single_jurisdiction",
        "has_divergence_outputs": False,
        "topic": {"id": "topic-1", "name": "Test", "description": "", "subject_tags": []},
        "clusters": [{"id": "cluster-1", "topic_id": "topic-1", "name": "C", "description": ""}],
        "run": {"id": "run-001", "workflow_mode": "single_jurisdiction"},
        "source_records": [],
        "sources": [],
        "propositions": props,
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "narrative": {"title": "T", "summary": "S", "sections": []},
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_mode_requested": "local",
                    "extraction_mode_effective": "local",
                },
                "outputs": {
                    "extraction_started_at": "2026-06-02T10:00:00Z",
                    "extraction_completed_at": "2026-06-02T10:05:00Z",
                    "extraction_jobs_total": 4,
                    "extraction_jobs_completed": 4,
                    "extraction_elapsed_seconds": 300,
                    "propositions_extracted": proposition_count,
                },
            }
        ],
        "proposition_extraction_jobs": [{"attempted_llm_calls": 2, "successful_llm_calls": 1}],
        "extraction_llm_call_traces": traces,
    }


def _demo_case_payload() -> dict:
    case_path = _REPO_ROOT / "data/demo/example_case.json"
    if not case_path.is_file():
        pytest.skip("example_case.json missing")
    return json.loads(case_path.read_text(encoding="utf-8"))


def test_run_status_reports_missing_bundle(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    (run_dir / "case.json").write_text(json.dumps(case_data, indent=2), encoding="utf-8")

    report = build_run_status_report(run_dir)
    assert report.has_run_bundle is False
    assert report.proposition_count == 0
    assert report.appears_in_progress is False
    assert "run-case" in report.suggested_next_command

    result = RUNNER.invoke(app, ["run-status", str(run_dir)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "run_bundle.json: no" in result.stdout
    assert "Suggested next command:" in result.stdout


def test_run_status_reports_persisted_run_and_suggests_export(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=5)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )

    report = build_run_status_report(run_dir)
    assert report.has_run_bundle is True
    assert report.run_bundle_mtime is not None
    assert report.proposition_count == 5
    assert report.extraction_mode == "local"
    assert report.live_success == 2
    assert report.appears_in_progress is False
    assert report.suggested_next_command == f"law-proposition-extractor-run-case export-run {run_dir.resolve()}"

    result = RUNNER.invoke(app, ["run-status", str(run_dir)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "run_bundle.json: yes" in result.stdout
    assert "run_bundle.json mtime:" in result.stdout
    assert "Live LLM calls:" in result.stdout
    assert "Cached LLM results:" in result.stdout
    assert "Latest extraction progress:" in result.stdout
    assert "export-run" in result.stdout


def test_run_status_suggests_retry_for_cached_failures(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=0, cached_failed=3)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )

    report = build_run_status_report(run_dir)
    assert report.cached_failed == 3
    assert "--retry-failed-extraction-cache" in report.suggested_next_command


def test_run_status_detects_tmp_write_in_progress(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    (run_dir / "run_bundle.json.tmp").write_text("{}", encoding="utf-8")

    report = build_run_status_report(run_dir)
    assert report.appears_in_progress is True
    assert report.in_progress_reason is not None
    assert "run-status" in report.suggested_next_command


def test_suggest_next_command_prefers_export_for_clean_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    suggested = suggest_next_command(
        run_dir=run_dir,
        has_run_bundle=True,
        appears_in_progress=False,
        case_data=None,
        bundle=_local_llm_bundle(proposition_count=2),
        summary={
            "propositions": 2,
            "extraction_mode_effective": "local",
            "live_llm_calls_successful": 2,
            "live_llm_calls_failed": 0,
            "cached_llm_results_successful": 0,
            "cached_llm_results_failed": 0,
        },
    )
    assert suggested == f"law-proposition-extractor-run-case export-run {run_dir}"
