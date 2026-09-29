"""Summaries derived from proposition-extraction jobs and `extraction_llm_call_traces`."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from .extraction_empty_failure import RETRYABLE_EMPTY_FAILURE_TYPES


class ExtractionPlanFailure(RuntimeError):
    """Raised when LLM extraction cannot run for a structural reason (before model calls)."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        super().__init__(f"extraction_plan_failed:{reason}: {detail}")


def extraction_llm_call_traces_from_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows accumulated during LLM proposition extraction (`inputs.extraction_llm_call_traces`)."""
    top = bundle.get("extraction_llm_call_traces")
    if isinstance(top, list) and top:
        return [t for t in top if isinstance(t, dict)]
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("stage_name") or "") != "proposition extraction":
            continue
        inp = tr.get("inputs")
        if not isinstance(inp, dict):
            return []
        raw = inp.get("extraction_llm_call_traces")
        if not isinstance(raw, list):
            return []
        return [t for t in raw if isinstance(t, dict)]
    return []


def _cached_llm_result_failed(trace: dict[str, Any]) -> bool:
    if str(trace.get("skip_reason") or "") == "failed_chunk_cached":
        return True
    return trace.get("llm_cache_hit") == "failed_chunk_cached"


def _cached_llm_result_successful(trace: dict[str, Any]) -> bool:
    if _cached_llm_result_failed(trace):
        return False
    if trace.get("llm_cache_hit") is True:
        return True
    return (
        trace.get("llm_call_attempted") is False
        and trace.get("llm_invoked") is False
        and trace.get("llm_call_succeeded") is True
        and trace.get("llm_cache_hit") is not None
    )


def _live_llm_call_attempted(trace: dict[str, Any]) -> bool:
    if trace.get("skipped_llm") is True:
        return False
    if _cached_llm_result_successful(trace) or _cached_llm_result_failed(trace):
        return False
    if trace.get("llm_call_attempted") is True:
        return True
    return trace.get("llm_invoked") is True


def _live_llm_call_failed(trace: dict[str, Any]) -> bool:
    if not _live_llm_call_attempted(trace):
        return False
    if trace.get("model_error"):
        return True
    if trace.get("llm_call_succeeded") is False:
        return True
    return False


def _live_llm_call_successful(trace: dict[str, Any]) -> bool:
    if not _live_llm_call_attempted(trace):
        return False
    return not _live_llm_call_failed(trace)


def _first_attempt_failed_retryable_empty(trace: dict[str, Any]) -> bool:
    if int(trace.get("attempt_index") or 0) != 0:
        return False
    if not _live_llm_call_failed(trace):
        return False
    ft = str(trace.get("failure_type") or "").strip()
    return ft in RETRYABLE_EMPTY_FAILURE_TYPES


def _llm_call_attempted(trace: dict[str, Any]) -> bool:
    """Legacy alias: live model invocations only (excludes cache reuse)."""
    return _live_llm_call_attempted(trace)


def _llm_call_succeeded(trace: dict[str, Any]) -> bool:
    """Legacy alias: any successful LLM outcome (live or cached)."""
    return _live_llm_call_successful(trace) or _cached_llm_result_successful(trace)


def _empty_llm_trace_counter_fields() -> dict[str, int]:
    return {
        "live_llm_calls_attempted": 0,
        "live_llm_calls_successful": 0,
        "live_llm_calls_failed": 0,
        "cached_llm_results_successful": 0,
        "cached_llm_results_failed": 0,
        "cached_successful_llm_results": 0,
        "cached_failed_llm_results": 0,
        "llm_results_reused_from_cache": 0,
        "attempted_llm_calls": 0,
        "successful_llm_calls": 0,
        "failed_llm_calls": 0,
    }


def assert_extraction_llm_metrics_consistent(metrics: dict[str, Any]) -> None:
    """Validate live-call accounting: attempted == successful + failed."""
    live_attempted = int(metrics.get("live_llm_calls_attempted") or 0)
    live_success = int(metrics.get("live_llm_calls_successful") or 0)
    live_failed = int(metrics.get("live_llm_calls_failed") or 0)
    if live_attempted != live_success + live_failed:
        raise AssertionError(
            f"live_llm_calls_attempted ({live_attempted}) != "
            f"live_llm_calls_successful ({live_success}) + live_llm_calls_failed ({live_failed})"
        )
    cached_ok = int(metrics.get("cached_llm_results_successful") or 0)
    cached_fail = int(metrics.get("cached_llm_results_failed") or 0)
    reused = int(metrics.get("llm_results_reused_from_cache") or 0)
    if reused != cached_ok + cached_fail:
        raise AssertionError(
            f"llm_results_reused_from_cache ({reused}) != "
            f"cached_llm_results_successful ({cached_ok}) + cached_llm_results_failed ({cached_fail})"
        )


def build_extraction_llm_skip_trace(
    *,
    source_record_id: str,
    source_title: str | None = None,
    source_fragment_id: str | None = None,
    fragment_locator: str | None = None,
    extraction_mode: str,
    model_alias: str | None = None,
    skip_reason: str,
    configured_context_limit: int | None = None,
    estimated_input_tokens: int | None = None,
    extraction_llm_chunk_index: int | None = None,
    extraction_llm_chunk_total: int | None = None,
) -> dict[str, Any]:
    """Diagnostic row for a fragment/chunk where the model was not called."""
    return {
        "source_record_id": source_record_id,
        "source_title": source_title,
        "source_fragment_id": source_fragment_id,
        "fragment_locator": fragment_locator,
        "model_alias": model_alias,
        "configured_context_limit": configured_context_limit,
        "extraction_mode": extraction_mode,
        "estimated_input_tokens": estimated_input_tokens,
        "skipped_llm": True,
        "skip_reason": skip_reason,
        "llm_call_attempted": False,
        "llm_invoked": False,
        "llm_call_succeeded": False,
        "extraction_llm_chunk_index": extraction_llm_chunk_index,
        "extraction_llm_chunk_total": extraction_llm_chunk_total,
    }


def compute_extraction_llm_trace_summary_metrics(
    traces: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate diagnostics from `extraction_llm_call_traces` (no I/O)."""
    live_attempted = sum(1 for t in traces if _live_llm_call_attempted(t))
    live_success = sum(1 for t in traces if _live_llm_call_successful(t))
    live_failed = sum(1 for t in traces if _live_llm_call_failed(t))
    cached_success = sum(1 for t in traces if _cached_llm_result_successful(t))
    cached_failed = sum(1 for t in traces if _cached_llm_result_failed(t))
    skipped_count = sum(
        1
        for t in traces
        if t.get("skipped_llm") is True and not _cached_llm_result_failed(t)
    )
    ctx_risk_count = sum(1 for t in traces if str(t.get("skip_reason") or "") == "context_window_risk")

    positive_ests: list[tuple[int, dict[str, Any]]] = []
    for t in traces:
        est = t.get("estimated_input_tokens")
        if isinstance(est, int) and est > 0:
            positive_ests.append((est, t))

    max_tok: int | None = max((e for e, _ in positive_ests), default=None)

    locator: str | None = None
    record_id: str | None = None
    if positive_ests:
        _best_est, best_row = max(positive_ests, key=lambda x: x[0])
        frag = best_row.get("fragment_locator")
        if frag is not None and str(frag).strip():
            locator = str(frag).strip()
        sid = best_row.get("source_record_id")
        if sid is not None and str(sid).strip():
            record_id = str(sid).strip()

    reused = cached_success + cached_failed
    retry_attempted = sum(1 for t in traces if int(t.get("attempt_index") or 0) == 1)
    retry_successful = sum(
        1 for t in traces if int(t.get("attempt_index") or 0) == 1 and _live_llm_call_successful(t)
    )
    retry_failed = sum(
        1 for t in traces if int(t.get("attempt_index") or 0) == 1 and _live_llm_call_failed(t)
    )
    first_attempt_failed = sum(1 for t in traces if _first_attempt_failed_retryable_empty(t))
    result: dict[str, Any] = {
        "live_llm_calls_attempted": live_attempted,
        "live_llm_calls_successful": live_success,
        "live_llm_calls_failed": live_failed,
        "cached_llm_results_successful": cached_success,
        "cached_llm_results_failed": cached_failed,
        "cached_successful_llm_results": cached_success,
        "cached_failed_llm_results": cached_failed,
        "llm_results_reused_from_cache": reused,
        "attempted_llm_calls": live_attempted,
        "successful_llm_calls": live_success,
        "failed_llm_calls": live_failed,
        "llm_extraction_call_count": live_attempted,
        "llm_extraction_skipped_count": skipped_count,
        "max_estimated_input_tokens": max_tok,
        "context_window_risk_count": ctx_risk_count,
        "largest_extraction_fragment_locator": locator,
        "largest_extraction_source_record_id": record_id,
        "first_attempt_failed": first_attempt_failed,
        "retry_attempted": retry_attempted,
        "retry_successful": retry_successful,
        "retry_failed": retry_failed,
    }
    assert_extraction_llm_metrics_consistent(result)
    return result


def _job_was_executed(row: dict[str, Any]) -> bool:
    if not row.get("selected_for_extraction"):
        return False
    if row.get("llm_invoked") is True:
        return True
    if int(row.get("proposition_count") or 0) > 0:
        return True
    status = str(row.get("cache_status") or "")
    return status in {"chunk_cache_hit", "content_hash_reuse", "chunk_cache_miss", "failed_chunk_cached"}


def _job_failed(row: dict[str, Any]) -> bool:
    if not row.get("selected_for_extraction"):
        return False
    prop_count = int(row.get("proposition_count") or 0)
    if prop_count > 0:
        return False
    if row.get("errors"):
        return True
    if row.get("llm_invoked") and prop_count == 0:
        return True
    if str(row.get("cache_status") or "") == "failed_chunk_cached":
        return True
    if row.get("repairable") and row.get("repair_reason"):
        return True
    warnings = row.get("warnings")
    if isinstance(warnings, list) and warnings:
        return True
    return False


def _job_cached_success(row: dict[str, Any]) -> bool:
    status = str(row.get("cache_status") or "")
    if status in {"chunk_cache_hit", "aggregate_cache_hit", "content_hash_reuse"}:
        return int(row.get("proposition_count") or 0) > 0
    return False


def compute_extraction_job_metrics(jobs: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Aggregate per-fragment extraction job rows (audit / summary)."""
    job_rows = [row for row in jobs if isinstance(row, dict)]
    created = len(job_rows)
    selected = sum(1 for row in job_rows if row.get("selected_for_extraction"))
    executed = sum(1 for row in job_rows if _job_was_executed(row))
    skipped = created - selected
    successful = sum(
        1 for row in job_rows if row.get("selected_for_extraction") and int(row.get("proposition_count") or 0) > 0
    )
    failed = sum(1 for row in job_rows if _job_failed(row))
    cached = sum(1 for row in job_rows if _job_cached_success(row))
    return {
        "extraction_jobs_created": created,
        "extraction_jobs_selected": selected,
        "extraction_jobs_executed": executed,
        "extraction_jobs_skipped": skipped,
        "extraction_jobs_total": created,
        "extraction_jobs_successful": successful,
        "extraction_jobs_failed": failed,
        "extraction_jobs_cached": cached,
    }


def compute_skip_reasons_by_type(
    jobs: Sequence[dict[str, Any]],
    llm_traces: Sequence[dict[str, Any]],
) -> dict[str, int]:
    """Count skip reasons from job rows and pre-call LLM diagnostic traces."""
    counts: Counter[str] = Counter()
    for row in jobs:
        if not isinstance(row, dict):
            continue
        if row.get("selected_for_extraction"):
            continue
        reason = str(row.get("skip_reason") or row.get("selection_reason") or "unknown").strip() or "unknown"
        counts[reason] += 1
    for trace in llm_traces:
        if not isinstance(trace, dict):
            continue
        if trace.get("skipped_llm") is not True:
            continue
        reason = str(trace.get("skip_reason") or "unknown").strip() or "unknown"
        counts[reason] += 1
    return dict(sorted(counts.items()))


def merge_extraction_observability_metrics(
    *,
    jobs: Sequence[dict[str, Any]],
    llm_traces: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Job-plan metrics plus LLM trace metrics and skip_reason histogram."""
    merged: dict[str, Any] = dict(compute_extraction_job_metrics(jobs))
    merged.update(compute_extraction_llm_trace_summary_metrics(llm_traces))
    merged["skip_reasons_by_type"] = compute_skip_reasons_by_type(jobs, llm_traces)
    return merged


def build_extraction_job_inspection(
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """Operator-facing extraction job / trace summary from an exported or in-memory bundle."""
    jobs = bundle.get("proposition_extraction_jobs")
    job_rows = [row for row in jobs if isinstance(row, dict)] if isinstance(jobs, list) else []
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    top_traces = bundle.get("extraction_llm_call_traces")
    if isinstance(top_traces, list) and top_traces:
        llm_traces = [t for t in top_traces if isinstance(t, dict)] or llm_traces
    fragments = bundle.get("source_fragments")
    fragment_count = len(fragments) if isinstance(fragments, list) else 0
    metrics = merge_extraction_observability_metrics(jobs=job_rows, llm_traces=llm_traces)
    metrics["source_fragments_total"] = fragment_count
    pex_inputs: dict[str, Any] = {}
    for tr in bundle.get("stage_traces") or []:
        if isinstance(tr, dict) and str(tr.get("stage_name") or "") == "proposition extraction":
            inp = tr.get("inputs")
            if isinstance(inp, dict):
                pex_inputs = inp
            break
    sample_unselected = [
        {
            "source_record_id": row.get("source_record_id"),
            "fragment_locator": row.get("fragment_locator"),
            "skip_reason": row.get("skip_reason"),
            "selection_reason": row.get("selection_reason"),
        }
        for row in job_rows
        if not row.get("selected_for_extraction")
    ][:12]
    sample_selected_not_invoked = [
        {
            "source_record_id": row.get("source_record_id"),
            "fragment_locator": row.get("fragment_locator"),
            "cache_status": row.get("cache_status"),
            "llm_invoked": row.get("llm_invoked"),
            "proposition_count": row.get("proposition_count"),
        }
        for row in job_rows
        if row.get("selected_for_extraction") and not row.get("llm_invoked")
    ][:12]
    return {
        "metrics": metrics,
        "extraction_mode_effective": pex_inputs.get("extraction_mode_effective")
        or pex_inputs.get("extraction_mode"),
        "extraction_fallback": pex_inputs.get("extraction_fallback"),
        "effective_focus_terms": pex_inputs.get("effective_focus_terms"),
        "effective_fragment_selection_mode": pex_inputs.get("effective_fragment_selection_mode"),
        "derived_artifact_cache_status": (pex_inputs.get("derived_artifact_cache") or {}).get("cache_status")
        if isinstance(pex_inputs.get("derived_artifact_cache"), dict)
        else None,
        "sample_unselected_jobs": sample_unselected,
        "sample_selected_without_llm_invoke": sample_selected_not_invoked,
    }


def _compact_stage_counts(trace: dict[str, Any]) -> dict[str, Any]:
    stage = str(trace.get("stage_name") or "")
    inputs = trace.get("inputs") if isinstance(trace.get("inputs"), dict) else {}
    outputs = trace.get("outputs") if isinstance(trace.get("outputs"), dict) else {}
    counts: dict[str, Any] = {}
    if stage == "source intake":
        for key in ("sources_total", "sources_fetched", "sources_cached", "sources_failed"):
            if key in outputs:
                counts[key] = outputs[key]
        if not counts and isinstance(inputs.get("sources"), list):
            counts["sources_total"] = len(inputs["sources"])
    elif stage == "proposition extraction":
        for key in (
            "extraction_jobs_created",
            "extraction_jobs_selected",
            "extraction_jobs_executed",
            "extraction_jobs_failed",
            "propositions_extracted",
            "live_llm_calls_attempted",
            "live_llm_calls_successful",
            "live_llm_calls_failed",
            "cached_llm_results_successful",
            "cached_llm_results_failed",
        ):
            if key in inputs:
                counts[key] = inputs[key]
            elif key in outputs:
                counts[key] = outputs[key]
    elif stage == "source parsing":
        for key in ("source_parse_trace_count", "source_fragment_count"):
            if key in outputs:
                counts[key] = outputs[key]
    return counts


def summarize_stage_traces_compact(
    trace_entries: list[dict[str, Any]],
    *,
    extraction_job_inspection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact operator view of stage traces (no full inputs/outputs blobs)."""
    compact_traces: list[dict[str, Any]] = []
    for entry in trace_entries:
        raw = entry.get("trace")
        trace = raw if isinstance(raw, dict) else {}
        errors = [str(x) for x in (trace.get("errors") or []) if str(x).strip()]
        warnings = [str(x) for x in (trace.get("warnings") or []) if str(x).strip()]
        status = "failed" if errors else ("warning" if warnings else "ok")
        row: dict[str, Any] = {
            "order": entry.get("order"),
            "stage_name": entry.get("stage_name") or trace.get("stage_name"),
            "storage_uri": entry.get("storage_uri"),
            "status": status,
            "timestamp": trace.get("timestamp"),
            "duration_ms": trace.get("duration_ms"),
            "strategy_used": trace.get("strategy_used"),
            "model_alias_used": trace.get("model_alias_used"),
            "key_counts": _compact_stage_counts(trace),
        }
        if errors:
            row["errors"] = errors[:8]
        if warnings:
            row["warnings"] = warnings[:8]
        skip_hist = trace.get("inputs", {}).get("skip_reasons_by_type")
        if isinstance(skip_hist, dict) and skip_hist:
            row["skip_reasons_by_type"] = skip_hist
        compact_traces.append(row)
    out: dict[str, Any] = {
        "trace_count": len(compact_traces),
        "traces": compact_traces,
    }
    if extraction_job_inspection is not None:
        out["extraction_job_inspection"] = extraction_job_inspection
    return out


def validate_llm_extraction_job_plan(
    *,
    extraction_mode: str,
    extraction_fallback: str,
    extraction_jobs_created: int,
    extraction_jobs_selected: int,
    source_fragments_total: int,
    sources_count: int,
    focus_terms: list[str],
    required_locators: set[str],
    fragment_selection_mode: str,
    has_authoritative_text: bool,
) -> None:
    """Raise ``ExtractionPlanFailure`` when LLM extraction cannot proceed structurally."""
    if extraction_mode not in {"local", "frontier"}:
        return
    if extraction_jobs_created == 0:
        if source_fragments_total == 0 and not has_authoritative_text:
            raise ExtractionPlanFailure(
                "no_extractable_fragments",
                f"{sources_count} source(s) but no fragments and no authoritative text to extract.",
            )
        raise ExtractionPlanFailure(
            "no_extraction_jobs_created",
            f"0 extraction jobs for {sources_count} source(s) and {source_fragments_total} fragment(s).",
        )
    if extraction_jobs_selected == 0:
        if fragment_selection_mode == "required_plus_focus" and not focus_terms and not required_locators:
            raise ExtractionPlanFailure(
                "no_focus_terms",
                "fragment_selection_mode=required_plus_focus but focus_terms and "
                "required_fragment_locators are both empty — no fragments selected.",
            )
        if fragment_selection_mode == "required_only" and not required_locators:
            raise ExtractionPlanFailure(
                "no_selected_fragments",
                "fragment_selection_mode=required_only but required_fragment_locators is empty.",
            )
        raise ExtractionPlanFailure(
            "no_selected_fragments",
            f"{extraction_jobs_created} extraction job(s) created but none selected for "
            f"{extraction_mode} extraction (mode={fragment_selection_mode!r}).",
        )
