"""Aggregation of extraction_llm_call_traces into CLI / run-quality summaries."""

from law_proposition_extractor_pipeline.cli_run_summary import build_cli_completion_summary
from law_proposition_extractor_pipeline.extraction_llm_metrics import (
    assert_extraction_llm_metrics_consistent,
    compute_extraction_job_metrics,
    compute_extraction_llm_trace_summary_metrics,
    extraction_llm_call_traces_from_bundle,
    merge_extraction_observability_metrics,
)
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary


def test_compute_extraction_job_metrics_counts() -> None:
    jobs = [
        {"selected_for_extraction": True, "llm_invoked": True, "proposition_count": 2},
        {"selected_for_extraction": True, "llm_invoked": False, "proposition_count": 0},
        {"selected_for_extraction": False, "skip_reason": "no_focus_match"},
    ]
    m = compute_extraction_job_metrics(jobs)
    assert m["extraction_jobs_created"] == 3
    assert m["extraction_jobs_selected"] == 2
    assert m["extraction_jobs_executed"] == 1
    assert m["extraction_jobs_skipped"] == 1


def test_merge_extraction_observability_includes_skip_histogram() -> None:
    jobs = [{"selected_for_extraction": False, "skip_reason": "too_short"}]
    traces = [{"skipped_llm": True, "skip_reason": "empty_source_text"}]
    merged = merge_extraction_observability_metrics(jobs=jobs, llm_traces=traces)
    assert merged["llm_extraction_skipped_count"] == 1
    assert merged["skip_reasons_by_type"]["too_short"] == 1
    assert merged["skip_reasons_by_type"]["empty_source_text"] == 1


def test_compute_metrics_empty_traces() -> None:
    m = compute_extraction_llm_trace_summary_metrics([])
    assert m["attempted_llm_calls"] == 0
    assert m["live_llm_calls_attempted"] == 0
    assert m["cached_llm_results_successful"] == 0
    assert m["llm_results_reused_from_cache"] == 0
    assert_extraction_llm_metrics_consistent(m)


def test_compute_metrics_cache_success_not_counted_as_live_success() -> None:
    traces = [
        {"llm_call_attempted": True, "llm_invoked": True, "llm_call_succeeded": False, "model_error": "err"},
    ] * 3 + [
        {
            "llm_cache_hit": True,
            "llm_call_attempted": False,
            "llm_invoked": False,
            "llm_call_succeeded": True,
        },
    ] * 2
    m = compute_extraction_llm_trace_summary_metrics(traces)
    assert m["live_llm_calls_attempted"] == 3
    assert m["live_llm_calls_successful"] == 0
    assert m["live_llm_calls_failed"] == 3
    assert m["cached_llm_results_successful"] == 2
    assert m["attempted_llm_calls"] == m["successful_llm_calls"] + m["failed_llm_calls"]


def test_compute_metrics_attempted_uses_llm_call_attempted_before_invoke() -> None:
    traces = [
        {
            "llm_call_attempted": True,
            "llm_invoked": False,
            "llm_call_succeeded": False,
            "model_error": "timeout",
        }
    ]
    m = compute_extraction_llm_trace_summary_metrics(traces)
    assert m["attempted_llm_calls"] == 1
    assert m["successful_llm_calls"] == 0
    assert m["failed_llm_calls"] == 1


def test_compute_metrics_calls_skips_and_context_risk() -> None:
    traces = [
        {
            "estimated_input_tokens": 100,
            "skipped_llm": False,
            "llm_invoked": True,
            "fragment_locator": "doc:a",
            "source_record_id": "src-a",
            "skip_reason": None,
        },
        {
            "estimated_input_tokens": 900,
            "skipped_llm": False,
            "llm_invoked": True,
            "fragment_locator": "doc:b",
            "source_record_id": "src-b",
            "skip_reason": None,
        },
        {
            "estimated_input_tokens": -1,
            "skipped_llm": True,
            "llm_invoked": False,
            "fragment_locator": "doc:c",
            "source_record_id": "src-c",
            "skip_reason": "context_window_risk",
        },
    ]
    m = compute_extraction_llm_trace_summary_metrics(traces)
    assert m["attempted_llm_calls"] == 2
    assert m["successful_llm_calls"] == 2
    assert m["failed_llm_calls"] == 0
    assert m["llm_extraction_call_count"] == 2
    assert m["llm_extraction_skipped_count"] == 1
    assert m["context_window_risk_count"] == 1
    assert m["max_estimated_input_tokens"] == 900
    assert m["largest_extraction_fragment_locator"] == "doc:b"
    assert m["largest_extraction_source_record_id"] == "src-b"


def test_compute_metrics_ignores_non_positive_estimates_for_max_and_largest() -> None:
    traces = [
        {
            "estimated_input_tokens": -1,
            "skipped_llm": True,
            "llm_invoked": False,
            "skip_reason": "context_window_risk",
            "fragment_locator": "frag-x",
            "source_record_id": "rec-x",
        },
        {
            "estimated_input_tokens": 0,
            "skipped_llm": True,
            "llm_invoked": False,
            "skip_reason": "",
            "fragment_locator": "frag-y",
            "source_record_id": "rec-y",
        },
    ]
    m = compute_extraction_llm_trace_summary_metrics(traces)
    assert m["max_estimated_input_tokens"] is None
    assert m["largest_extraction_fragment_locator"] is None
    assert m["largest_extraction_source_record_id"] is None
    assert m["context_window_risk_count"] == 1


def test_extraction_llm_call_traces_from_bundle_reads_proposition_stage() -> None:
    bundle: dict = {
        "stage_traces": [
            {"stage_name": "other", "inputs": {"extraction_llm_call_traces": [{"bogus": True}]}},
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "frontier",
                    "extraction_llm_call_traces": [
                        {"llm_invoked": True},
                        "not-a-dict",
                    ],
                },
            },
        ]
    }
    rows = extraction_llm_call_traces_from_bundle(bundle)
    assert rows == [{"llm_invoked": True}]


def test_build_cli_completion_summary_includes_llm_metrics_for_frontier() -> None:
    bundle: dict = {
        "source_records": [{"id": "s1"}],
        "propositions": [],
        "proposition_extraction_traces": [],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "frontier",
                    "extraction_llm_call_traces": [
                        {
                            "estimated_input_tokens": 500,
                            "skipped_llm": False,
                            "llm_invoked": True,
                            "fragment_locator": "loc-z",
                            "source_record_id": "rec-z",
                        }
                    ],
                },
            }
        ],
    }
    summary = build_cli_completion_summary(
        bundle, quality_summary={"status": "pass", "warning_count": 0}, output_dir="/out"
    )
    assert summary["extraction_mode"] == "frontier"
    assert summary["llm_extraction_call_count"] == 1
    assert summary["max_estimated_input_tokens"] == 500
    assert summary["largest_extraction_fragment_locator"] == "loc-z"


def test_build_cli_completion_summary_omits_llm_metrics_for_heuristic() -> None:
    bundle: dict = {
        "source_records": [],
        "propositions": [],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "heuristic",
                    "extraction_llm_call_traces": [{"llm_invoked": True}],
                },
            }
        ],
    }
    summary = build_cli_completion_summary(
        bundle, quality_summary={"status": "pass", "warning_count": 0}, output_dir=""
    )
    assert "llm_extraction_call_count" not in summary


def test_build_run_quality_summary_merges_llm_metrics_when_frontier() -> None:
    bundle: dict = {
        "run": {"id": "r1"},
        "source_records": [],
        "propositions": [],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_llm_call_traces": [
                        {
                            "estimated_input_tokens": 120,
                            "skipped_llm": False,
                            "llm_invoked": True,
                            "fragment_locator": "p1",
                            "source_record_id": "src1",
                        }
                    ],
                },
            }
        ],
    }
    rq = build_run_quality_summary(bundle, lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0})
    met = rq["metrics"]
    assert met["llm_extraction_call_count"] == 1
    assert met["max_estimated_input_tokens"] == 120
    assert met["largest_extraction_fragment_locator"] == "p1"


def test_build_cli_completion_summary_includes_derived_cache_dir() -> None:
    bundle: dict = {
        "source_records": [{"id": "s1"}],
        "propositions": [],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "derived_artifact_cache": {"cache_dir": "/tmp/lpe-derived"},
                    "extraction_llm_call_traces": [],
                },
            }
        ],
    }
    summary = build_cli_completion_summary(
        bundle, quality_summary={"status": "pass", "warning_count": 0}, output_dir=""
    )
    assert summary.get("derived_cache_dir") == "/tmp/lpe-derived"


def test_run_quality_fails_when_no_llm_attempts_for_selected_jobs() -> None:
    bundle: dict = {
        "run": {"id": "r4"},
        "source_records": [{"id": "s1"}],
        "propositions": [],
        "proposition_extraction_jobs": [
            {"selected_for_extraction": True, "source_record_id": "s1"},
        ],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_llm_call_traces": [
                        {"skipped_llm": True, "skip_reason": "empty_source_text"},
                    ],
                },
            }
        ],
    }
    rq = build_run_quality_summary(
        bundle,
        lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    assert rq["status"] == "fail"
    assert "No LLM extraction calls were attempted" in rq["recommendations"][0]


def test_run_quality_failed_chunk_cached_recommendation_includes_retry_hint() -> None:
    bundle: dict = {
        "run": {"id": "r5"},
        "source_records": [{"id": "s1"}],
        "propositions": [],
        "proposition_extraction_jobs": [
            {"selected_for_extraction": True, "source_record_id": "s1"},
        ],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "derived_artifact_cache": {"cache_dir": "/cache/run-a"},
                    "extraction_llm_call_traces": [
                        {"skipped_llm": True, "skip_reason": "failed_chunk_cached"},
                    ],
                },
            }
        ],
    }
    rq = build_run_quality_summary(
        bundle,
        lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    assert rq["status"] == "fail"
    rec = " ".join(rq["recommendations"])
    assert "--retry-failed-extraction-cache" in rec
    assert "proposition_extraction_chunk" in rec


def test_run_quality_fails_when_all_llm_calls_failed_but_fallback_used() -> None:
    bundle: dict = {
        "run": {"id": "r3"},
        "source_records": [{"id": "s1"}],
        "propositions": [{"id": "p1"}],
        "proposition_extraction_traces": [{"fallback_used": True}],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_mode_requested": "local",
                    "extraction_mode_effective": "local",
                    "extraction_llm_call_traces": [
                        {"llm_invoked": True, "model_error": "Error code: 400"},
                    ],
                },
            }
        ],
    }
    rq = build_run_quality_summary(
        bundle,
        lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    assert rq["status"] == "fail"
    assert "No successful LLM extraction occurred." in rq["recommendations"]
    assert rq["metrics"]["successful_llm_calls"] == 0
    assert rq["metrics"]["fallback_count"] == 1


def test_build_run_quality_summary_no_llm_metric_keys_for_unknown_mode() -> None:
    bundle: dict = {
        "run": {"id": "r2"},
        "source_records": [],
        "propositions": [],
    }
    rq = build_run_quality_summary(bundle, lint_report={"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0})
    assert "llm_extraction_call_count" not in rq["metrics"]
