"""Pure helpers for CLI completion summary (testable without Rich)."""

from __future__ import annotations

from typing import Any

from .extraction_llm_metrics import (
    extraction_llm_call_traces_from_bundle,
    merge_extraction_observability_metrics,
)
from .extraction_progress import extraction_timing_metrics_from_bundle
from .llm_extraction_config import format_failed_chunk_cache_operator_hint


def derived_cache_dir_from_bundle(bundle: dict[str, Any]) -> str | None:
    """Resolved derived artifact cache directory from the proposition extraction stage."""
    inp = _proposition_extraction_stage_inputs(bundle)
    if inp is None:
        return None
    hook = inp.get("derived_artifact_cache")
    if isinstance(hook, dict):
        raw = hook.get("cache_dir")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("stage_name") or "") != "source intake":
            continue
        inputs = tr.get("inputs")
        if not isinstance(inputs, dict):
            continue
        raw = inputs.get("derived_cache_dir")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _proposition_extraction_stage_inputs(bundle: dict[str, Any]) -> dict[str, Any] | None:
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("stage_name") or "") != "proposition extraction":
            continue
        inp = tr.get("inputs")
        return inp if isinstance(inp, dict) else None
    return None


def extraction_mode_from_bundle(bundle: dict[str, Any]) -> str:
    inp = _proposition_extraction_stage_inputs(bundle)
    if inp is None:
        return "unknown"
    effective = inp.get("extraction_mode_effective") or inp.get("extraction_mode")
    if effective is not None and str(effective).strip():
        return str(effective).strip()
    return "unknown"


def extraction_mode_requested_from_bundle(bundle: dict[str, Any]) -> str:
    inp = _proposition_extraction_stage_inputs(bundle)
    if inp is None:
        return "unknown"
    requested = inp.get("extraction_mode_requested")
    if requested is not None and str(requested).strip():
        return str(requested).strip()
    mode = inp.get("extraction_mode")
    if mode is not None and str(mode).strip():
        return str(mode).strip()
    return "unknown"


def count_extraction_fallback_traces(bundle: dict[str, Any]) -> int:
    traces = bundle.get("proposition_extraction_traces")
    if not isinstance(traces, list):
        return 0
    return sum(1 for t in traces if isinstance(t, dict) and t.get("fallback_used"))


def count_low_confidence_extraction_traces(bundle: dict[str, Any]) -> int:
    traces = bundle.get("proposition_extraction_traces")
    if not isinstance(traces, list):
        return 0
    return sum(
        1 for t in traces if isinstance(t, dict) and str(t.get("confidence") or "").lower() == "low"
    )


def build_cli_completion_summary(
    bundle: dict[str, Any],
    *,
    quality_summary: dict[str, Any],
    output_dir: str | None,
) -> dict[str, Any]:
    sources = bundle.get("source_records")
    if not isinstance(sources, list):
        sources = bundle.get("sources")
    n_sources = len(sources) if isinstance(sources, list) else 0
    props = bundle.get("propositions")
    n_props = len(props) if isinstance(props, list) else 0
    ext_effective = extraction_mode_from_bundle(bundle)
    ext_requested = extraction_mode_requested_from_bundle(bundle)
    fallback_count = count_extraction_fallback_traces(bundle)
    summary: dict[str, Any] = {
        "sources": n_sources,
        "propositions": n_props,
        "extraction_mode": ext_effective,
        "extraction_mode_requested": ext_requested,
        "extraction_mode_effective": ext_effective,
        "fallback_count": fallback_count,
        "low_confidence_count": count_low_confidence_extraction_traces(bundle),
        "validation_warning_count": int(quality_summary.get("warning_count") or 0),
        "output_directory": output_dir or "",
        "run_quality_status": str(quality_summary.get("status") or "unknown"),
    }
    if ext_effective in {"local", "frontier"}:
        jobs = bundle.get("proposition_extraction_jobs")
        job_rows = [row for row in jobs if isinstance(row, dict)] if isinstance(jobs, list) else []
        llm_traces = extraction_llm_call_traces_from_bundle(bundle)
        llm_metrics = merge_extraction_observability_metrics(jobs=job_rows, llm_traces=llm_traces)
        fragments = bundle.get("source_fragments")
        llm_metrics["source_fragments_total"] = (
            len(fragments) if isinstance(fragments, list) else 0
        )
        llm_metrics.update(extraction_timing_metrics_from_bundle(bundle))
        summary.update(llm_metrics)
        derived_dir = derived_cache_dir_from_bundle(bundle)
        if derived_dir:
            summary["derived_cache_dir"] = derived_dir
        any_llm_success = int(llm_metrics.get("live_llm_calls_successful") or 0) + int(
            llm_metrics.get("cached_llm_results_successful") or 0
        )
        if any_llm_success == 0 and fallback_count > 0:
            summary["run_quality_status"] = "fail"
            summary["llm_extraction_failure_message"] = "No successful LLM extraction occurred."
        elif (
            int(llm_metrics.get("live_llm_calls_attempted") or llm_metrics.get("attempted_llm_calls") or 0) == 0
            and int(llm_metrics.get("extraction_jobs_selected") or 0) > 0
            and int(summary.get("propositions") or 0) == 0
        ):
            summary["run_quality_status"] = "fail"
            skip_hist = llm_metrics.get("skip_reasons_by_type")
            cache_hint = ""
            if isinstance(skip_hist, dict):
                cache_hint = format_failed_chunk_cache_operator_hint(
                    derived_cache_dir=derived_dir,
                    skip_reasons_by_type=skip_hist,
                )
            summary["llm_extraction_failure_message"] = (
                f"No LLM extraction calls were attempted for "
                f"{llm_metrics['extraction_jobs_selected']} selected job(s)."
                + (f" {cache_hint}" if cache_hint else "")
            )
    return summary
