"""Extraction progress, ETA, and timing metrics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from law_proposition_extractor_pipeline.extraction_progress import (
    ExtractionProgressTracker,
    ExtractionRunPlan,
    ExtractionSourcePlan,
    build_extraction_run_plan,
    compute_eta_seconds,
    compute_percent_complete,
    format_checkpoint_line,
    format_dry_run_estimate,
    format_progress_compact,
    extraction_timing_metrics_from_bundle,
    load_extraction_timing_profile,
    merge_timing_metrics_into_observability,
    persist_extraction_timing_profile,
)
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary


def _plan(total: int = 10, *, progress_every: int = 5) -> ExtractionRunPlan:
    return ExtractionRunPlan(
        total_jobs=total,
        selected_jobs=8,
        estimated_input_tokens=120_000,
        extraction_mode="local",
        sources=[
            ExtractionSourcePlan(
                source_index=1,
                source_id="src-a",
                source_title="Reg A",
                jobs_in_source=total,
            )
        ],
        progress_every=progress_every,
    )


def test_compute_eta_seconds_uses_completed_durations() -> None:
    eta = compute_eta_seconds(
        completed_jobs=2,
        total_jobs=10,
        elapsed_seconds=40.0,
        job_durations=[18.0, 22.0],
    )
    assert eta == pytest.approx(8 * 20.0)


def test_compute_eta_seconds_no_divide_by_zero_before_first_job() -> None:
    assert compute_eta_seconds(
        completed_jobs=0,
        total_jobs=10,
        elapsed_seconds=0.0,
        job_durations=[],
    ) is None
    assert compute_percent_complete(0, 10) == 0.0


def test_progress_formatter_shows_job_percent_elapsed_remaining() -> None:
    tracker = ExtractionProgressTracker(
        plan=_plan(total=4),
        progress_every=2,
        started_at=datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC),
        started_perf=1000.0,
    )
    tracker.counters.completed_jobs = 1
    tracker.counters.job_durations = [25.0]
    tracker.counters.propositions_so_far = 3
    tracker._llm_traces = [
        {"llm_call_attempted": True, "llm_call_succeeded": True, "llm_invoked": True},
    ]

    class _Clock:
        @staticmethod
        def counter() -> float:
            return 1025.0

    import law_proposition_extractor_pipeline.extraction_progress as ep

    monkey = pytest.MonkeyPatch()
    monkey.setattr(ep, "perf_counter", _Clock.counter)
    try:
        snap = tracker.snapshot(
            overall_job_index=2,
            source_id="src-a",
            source_title="Reg A",
            fragment_locator="regulation:10",
            model_call="local_extract",
            estimated_input_tokens=1129,
            chunk_index=1,
            chunk_total=1,
        )
    finally:
        monkey.undo()

    text = format_progress_compact(snap)
    assert "2/4" in text
    assert "25.0%" in text or "50.0%" in text
    assert "Elapsed:" in text
    assert "avg/job:" in text
    assert "remaining:" in text
    assert "ETA:" in text
    assert "regulation:10" in text
    assert "Propositions so far: 3" in text


def test_checkpoint_line_after_jobs_complete() -> None:
    tracker = ExtractionProgressTracker(plan=_plan(total=20, progress_every=10))
    for i in range(9):
        tracker.finish_job(
            source_id="src-a",
            source_title="Reg A",
            fragment_locator=f"loc:{i}",
            duration_seconds=10.0,
        )
    assert tracker.finish_job(
        source_id="src-a",
        source_title="Reg A",
        fragment_locator="loc:9",
        duration_seconds=10.0,
        traces=[{"skipped_llm": True, "skip_reason": "cached"}],
    ) is True
    snap = tracker.snapshot(
        overall_job_index=10,
        source_id="src-a",
        source_title="Reg A",
        fragment_locator="loc:9",
        model_call="local_extract",
    )
    line = format_checkpoint_line(snap)
    assert line.startswith("✓ 10/20 jobs complete")
    assert "1 skipped" in line


def test_progress_with_failed_and_skipped_calls() -> None:
    tracker = ExtractionProgressTracker(plan=_plan(total=3))
    tracker.finish_job(
        source_id="src-a",
        source_title="Reg A",
        fragment_locator="a",
        traces=[{"llm_call_attempted": True, "llm_call_succeeded": True, "llm_invoked": True}],
    )
    tracker.finish_job(
        source_id="src-a",
        source_title="Reg A",
        fragment_locator="b",
        traces=[{"llm_call_attempted": True, "llm_invoked": True, "model_error": "timeout"}],
    )
    tracker.finish_job(
        source_id="src-a",
        source_title="Reg A",
        fragment_locator="c",
        traces=[{"skipped_llm": True, "skip_reason": "context_window_risk"}],
    )
    metrics = tracker.timing_metrics()
    assert metrics["live_llm_calls_successful"] == 1
    assert metrics["live_llm_calls_failed"] == 1
    assert metrics["llm_extraction_skipped_count"] == 1
    assert metrics["extraction_jobs_completed"] == 3
    assert metrics["live_llm_calls_attempted"] == metrics["live_llm_calls_successful"] + metrics["live_llm_calls_failed"]


def test_run_quality_includes_timing_metrics_from_stage_outputs() -> None:
    bundle: dict = {
        "run": {"id": "r-timing"},
        "source_records": [{"id": "s1"}],
        "propositions": [{"id": "p1"}],
        "proposition_extraction_jobs": [
            {"selected_for_extraction": True, "llm_invoked": True, "proposition_count": 1},
        ],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_llm_call_traces": [{"llm_invoked": True}],
                },
                "outputs": {
                    "attempted_llm_calls": 1,
                    "successful_llm_calls": 1,
                    "extraction_elapsed_seconds": 120.5,
                    "average_seconds_per_job": 20.1,
                    "extraction_jobs_total": 6,
                    "extraction_jobs_completed": 6,
                    "propositions_extracted": 1,
                },
            }
        ],
    }
    rq = build_run_quality_summary(
        bundle,
        lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    met = rq["metrics"]
    assert met["extraction_elapsed_seconds"] == 120.5
    assert met["average_seconds_per_job"] == 20.1
    assert met["propositions_extracted"] == 1


def test_merge_timing_metrics_does_not_overwrite_llm_call_counts() -> None:
    obs = {"attempted_llm_calls": 5, "successful_llm_calls": 4}
    timing = {
        "attempted_llm_calls": 1,
        "extraction_elapsed_seconds": 90.0,
        "average_seconds_per_job": 18.0,
    }
    merged = merge_timing_metrics_into_observability(obs, timing)
    assert merged["attempted_llm_calls"] == 5
    assert merged["extraction_elapsed_seconds"] == 90.0


def test_dry_run_estimate_without_profile() -> None:
    text = format_dry_run_estimate(
        selected_jobs=279,
        estimated_input_tokens=312_000,
        extraction_mode="local",
        timing_profile=None,
    )
    assert "Selected extraction jobs: 279" in text
    assert "312,000" in text
    assert "No previous timing profile found" in text
    assert "20–45s/job" in text


def test_dry_run_estimate_with_previous_profile(tmp_path: Path) -> None:
    profile = {"average_seconds_per_job": 22.9, "extraction_jobs_completed": 279}
    persist_extraction_timing_profile(
        tmp_path,
        {**profile, "extraction_mode": "local", "extraction_elapsed_seconds": 6380},
    )
    loaded = load_extraction_timing_profile(tmp_path)
    assert loaded is not None
    text = format_dry_run_estimate(
        selected_jobs=100,
        estimated_input_tokens=50_000,
        extraction_mode="local",
        timing_profile=loaded,
    )
    assert "Previous run average: 22.9s/job" in text
    assert "Rough estimate:" in text


def test_extraction_timing_metrics_from_bundle() -> None:
    bundle = {
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "outputs": {"extraction_elapsed_seconds": 10.0, "slowest_job_locator": "sched:1a"},
            }
        ]
    }
    assert extraction_timing_metrics_from_bundle(bundle)["slowest_job_locator"] == "sched:1a"


def test_build_extraction_run_plan_source_grouping() -> None:
    sources = [
        SimpleNamespace(id="s1", title="Title One"),
        SimpleNamespace(id="s2", title="Title Two"),
    ]
    jobs = [
        (sources[0], None),
        (sources[0], None),
        (sources[1], None),
    ]
    plan = build_extraction_run_plan(
        jobs,
        selected_jobs=2,
        estimated_input_tokens=1000,
        extraction_mode="local",
    )
    assert plan.total_jobs == 3
    assert len(plan.sources) == 2
    assert plan.sources[0].jobs_in_source == 2
    assert plan.sources[1].jobs_in_source == 1
