"""LLM extraction metrics must agree across progress, bundle summaries, and inspect."""

from __future__ import annotations

from law_proposition_extractor_pipeline.cli_run_summary import build_cli_completion_summary
from law_proposition_extractor_pipeline.extraction_llm_metrics import (
    assert_extraction_llm_metrics_consistent,
    build_extraction_job_inspection,
    compute_extraction_llm_trace_summary_metrics,
    merge_extraction_observability_metrics,
)
from law_proposition_extractor_pipeline.extraction_progress import (
    ExtractionProgressTracker,
    ExtractionRunPlan,
    ExtractionSourcePlan,
    merge_timing_metrics_into_observability,
)
from law_proposition_extractor_pipeline.export import _attach_export_run_metadata
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary

_LLM_COUNT_KEYS = (
    "live_llm_calls_attempted",
    "live_llm_calls_successful",
    "live_llm_calls_failed",
    "cached_llm_results_successful",
    "cached_llm_results_failed",
    "cached_successful_llm_results",
    "cached_failed_llm_results",
    "llm_results_reused_from_cache",
    "attempted_llm_calls",
    "successful_llm_calls",
    "failed_llm_calls",
)


def _sample_traces() -> list[dict]:
    return [
        {
            "llm_call_attempted": True,
            "llm_invoked": True,
            "llm_call_succeeded": True,
            "fragment_locator": "reg:1",
        },
        {
            "llm_call_attempted": True,
            "llm_invoked": True,
            "llm_call_succeeded": False,
            "model_error": "timeout",
            "fragment_locator": "reg:2",
        },
        {
            "llm_cache_hit": True,
            "llm_call_attempted": False,
            "llm_invoked": False,
            "llm_call_succeeded": True,
            "fragment_locator": "reg:3",
        },
        {
            "skipped_llm": True,
            "skip_reason": "context_window_risk",
            "fragment_locator": "reg:4",
        },
        {
            "llm_cache_hit": "failed_chunk_cached",
            "skipped_llm": True,
            "skip_reason": "failed_chunk_cached",
            "llm_call_attempted": False,
            "llm_invoked": False,
            "llm_call_succeeded": False,
            "fragment_locator": "reg:5",
        },
    ]


def _pick_counts(payload: dict) -> dict[str, int]:
    return {k: int(payload[k]) for k in _LLM_COUNT_KEYS if k in payload}


def _bundle_from_traces(traces: list[dict]) -> dict:
    return {
        "run": {"id": "r-metrics"},
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
                    "extraction_llm_call_traces": traces,
                },
                "outputs": {
                    "extraction_elapsed_seconds": 42.0,
                    "extraction_jobs_total": 3,
                    "extraction_jobs_completed": 3,
                },
            }
        ],
    }


def test_live_cache_and_skipped_metrics_partition_and_balance() -> None:
    traces = _sample_traces()
    m = compute_extraction_llm_trace_summary_metrics(traces)
    assert m["live_llm_calls_attempted"] == 2
    assert m["live_llm_calls_successful"] == 1
    assert m["live_llm_calls_failed"] == 1
    assert m["cached_llm_results_successful"] == 1
    assert m["cached_llm_results_failed"] == 1
    assert m["llm_results_reused_from_cache"] == 2
    assert m["attempted_llm_calls"] == m["live_llm_calls_attempted"]
    assert m["successful_llm_calls"] == m["live_llm_calls_successful"]
    assert m["failed_llm_calls"] == m["live_llm_calls_failed"]
    assert m["cached_successful_llm_results"] == m["cached_llm_results_successful"]
    assert_extraction_llm_metrics_consistent(m)


def test_all_summaries_agree_for_mixed_traces() -> None:
    traces = _sample_traces()
    trace_metrics = compute_extraction_llm_trace_summary_metrics(traces)
    expected = _pick_counts(trace_metrics)

    plan = ExtractionRunPlan(
        total_jobs=5,
        selected_jobs=5,
        estimated_input_tokens=100,
        extraction_mode="local",
        sources=[
            ExtractionSourcePlan(
                source_index=1,
                source_id="s1",
                source_title="T",
                jobs_in_source=3,
            )
        ],
    )
    tracker = ExtractionProgressTracker(plan=plan)
    for locator in ("reg:1", "reg:2", "reg:3", "reg:4", "reg:5"):
        job_traces = [t for t in traces if t.get("fragment_locator") == locator]
        tracker.finish_job(
            source_id="s1",
            source_title="T",
            fragment_locator=locator,
            traces=job_traces,
            duration_seconds=1.0,
        )
    timing = tracker.timing_metrics()
    assert _pick_counts(timing) == expected

    bundle = _bundle_from_traces(traces)
    observability = merge_extraction_observability_metrics(
        jobs=bundle["proposition_extraction_jobs"],
        llm_traces=traces,
    )
    merged = merge_timing_metrics_into_observability(observability, timing)
    assert _pick_counts(merged) == expected

    rq = build_run_quality_summary(
        bundle,
        lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    assert _pick_counts(rq["metrics"]) == expected

    cli = build_cli_completion_summary(bundle, quality_summary=rq, output_dir="/out")
    assert _pick_counts(cli) == expected

    inspection = build_extraction_job_inspection(bundle)
    assert _pick_counts(inspection["metrics"]) == expected

    _attach_export_run_metadata(bundle)
    assert _pick_counts(bundle["export_run_metadata"]) == expected
