"""Inspect extraction jobs, LLM call traces, and chunk failures from exported bundles."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .extraction_llm_metrics import (
    _cached_llm_result_failed,
    _cached_llm_result_successful,
    _job_cached_success,
    _job_failed,
    _live_llm_call_attempted,
    _live_llm_call_failed,
    _live_llm_call_successful,
    compute_extraction_job_metrics,
    extraction_llm_call_traces_from_bundle,
    merge_extraction_observability_metrics,
)
from .extraction_empty_failure import (
    GRANULAR_EMPTY_FAILURE_TYPES,
    POST_FILTER_REMOVED_ALL,
    classify_extraction_failure_type,
)
from .extraction_repair import (
    RepairableExtractionChunk,
    classify_repairable_failure_type,
    is_repairable_error_text,
    list_repairable_extraction_chunks,
)


@dataclass(frozen=True)
class ExtractionFailureRecord:
    source_record_id: str
    source_title: str | None
    source_fragment_id: str | None
    fragment_locator: str | None
    extraction_llm_chunk_index: int | None
    extraction_llm_chunk_total: int | None
    extraction_mode: str | None
    model_alias: str | None
    estimated_input_tokens: int | None
    failure_reason: str
    failure_type: str
    repairable: bool
    from_cache: bool
    job_id: str | None = None
    proposition_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _failure_blob_from_job(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("errors", "warnings", "parse_error_message", "repair_reason", "skip_reason"):
        raw = row.get(key)
        if isinstance(raw, list):
            parts.extend(str(x) for x in raw if str(x).strip())
        elif raw is not None and str(raw).strip():
            parts.append(str(raw))
    return " ".join(parts)


def _failure_blob_from_trace(row: dict[str, Any]) -> str:
    parts = [
        row.get("model_error"),
        row.get("skip_reason"),
        row.get("failure_reason"),
        row.get("error"),
        row.get("parse_error_message"),
    ]
    return " ".join(str(p) for p in parts if p is not None and str(p).strip())


def _trace_failed(row: dict[str, Any]) -> bool:
    if _cached_llm_result_failed(row):
        return True
    if _live_llm_call_failed(row):
        return True
    if row.get("skipped_llm") and str(row.get("skip_reason") or "") not in {
        "",
        "context_window_risk",
    }:
        return not _cached_llm_result_successful(row)
    return False


def _trace_from_cache(row: dict[str, Any]) -> bool:
    return _cached_llm_result_successful(row) or _cached_llm_result_failed(row)


def list_extraction_failure_records(bundle: dict[str, Any]) -> list[ExtractionFailureRecord]:
    """All failed extraction jobs/chunks, including those that produced no propositions."""
    jobs = [
        row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)
    ]
    llm_rows = extraction_llm_call_traces_from_bundle(bundle)
    failures_raw = [
        row for row in (bundle.get("proposition_extraction_failures") or []) if isinstance(row, dict)
    ]
    chunk_statuses = [
        row
        for row in (bundle.get("proposition_extraction_chunk_statuses") or [])
        if isinstance(row, dict)
    ]

    by_key: dict[tuple[str, str | None, str | None, int | None], ExtractionFailureRecord] = {}

    def record_key(record: ExtractionFailureRecord) -> tuple[str, str | None, str | None, int | None]:
        return (
            record.source_record_id,
            record.source_fragment_id,
            record.fragment_locator,
            record.extraction_llm_chunk_index,
        )

    def upsert(record: ExtractionFailureRecord) -> None:
        key = record_key(record)
        cur = by_key.get(key)
        if cur is None or len(record.failure_reason) > len(cur.failure_reason):
            by_key[key] = record

    for row in llm_rows:
        if not _trace_failed(row):
            continue
        blob = _failure_blob_from_trace(row)
        ftype = classify_extraction_failure_type(
            blob, explicit_failure_type=str(row.get("failure_type") or "") or None
        )
        sid = str(row.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = row.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        ci = row.get("extraction_llm_chunk_index")
        ct = row.get("extraction_llm_chunk_total")
        idx = int(ci) if isinstance(ci, int) else None
        tot = int(ct) if isinstance(ct, int) else None
        est = row.get("estimated_input_tokens")
        upsert(
            ExtractionFailureRecord(
                source_record_id=sid,
                source_title=str(row.get("source_title") or "").strip() or None,
                source_fragment_id=frag,
                fragment_locator=str(row.get("fragment_locator") or "").strip() or None,
                extraction_llm_chunk_index=idx,
                extraction_llm_chunk_total=tot,
                extraction_mode=str(row.get("extraction_mode") or "").strip() or None,
                model_alias=str(row.get("model_alias") or "").strip() or None,
                estimated_input_tokens=int(est) if isinstance(est, int) and est > 0 else None,
                failure_reason=blob or "extraction_llm_call_failed",
                failure_type=ftype,
                repairable=is_repairable_error_text(blob)
                or ftype
                in {
                    "json_parse_or_llm_failure",
                    "empty_model_response",
                    *GRANULAR_EMPTY_FAILURE_TYPES,
                    "schema_validation_error",
                    "failed_chunk_cached",
                    POST_FILTER_REMOVED_ALL,
                },
                from_cache=_trace_from_cache(row),
            )
        )

    def _has_failure_for_locator(source_id: str, locator: str | None) -> bool:
        loc = locator or None
        return any(
            record.source_record_id == source_id and record.fragment_locator == loc
            for record in by_key.values()
        )

    for job in jobs:
        if not _job_failed(job):
            continue
        locator = str(job.get("fragment_locator") or "").strip() or None
        sid = str(job.get("source_record_id") or "").strip()
        if sid and _has_failure_for_locator(sid, locator):
            continue
        blob = _failure_blob_from_job(job)
        ftype = classify_extraction_failure_type(
            blob, explicit_failure_type=str(job.get("failure_type") or "") or None
        )
        sid = str(job.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = job.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        est = job.get("estimated_input_tokens")
        upsert(
            ExtractionFailureRecord(
                source_record_id=sid,
                source_title=str(job.get("source_title") or "").strip() or None,
                source_fragment_id=frag,
                fragment_locator=str(job.get("fragment_locator") or "").strip() or None,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode=str(job.get("extraction_mode") or "").strip() or None,
                model_alias=str(job.get("model_alias") or "").strip() or None,
                estimated_input_tokens=int(est) if isinstance(est, int) and est > 0 else None,
                failure_reason=blob or "extraction_job_failed",
                failure_type=ftype,
                repairable=bool(job.get("repairable"))
                or is_repairable_error_text(blob)
                or ftype
                in {
                    "json_parse_or_llm_failure",
                    "empty_model_response",
                    *GRANULAR_EMPTY_FAILURE_TYPES,
                    "schema_validation_error",
                    POST_FILTER_REMOVED_ALL,
                },
                from_cache=str(job.get("cache_status") or "") == "failed_chunk_cached",
                job_id=str(job.get("id") or "").strip() or None,
                proposition_count=int(job.get("proposition_count") or 0),
            )
        )

    for failure in failures_raw:
        sid = str(failure.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = failure.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        if any(
            record.source_record_id == sid and record.source_fragment_id == frag
            for record in by_key.values()
        ):
            continue
        errs = failure.get("validation_errors")
        err_list = [str(x) for x in errs if str(x).strip()] if isinstance(errs, list) else []
        blob = " ".join(
            str(x)
            for x in [failure.get("failure_reason"), *err_list]
            if x is not None and str(x).strip()
        )
        ftype = classify_extraction_failure_type(blob)
        frag_raw = failure.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        upsert(
            ExtractionFailureRecord(
                source_record_id=sid,
                source_title=None,
                source_fragment_id=frag,
                fragment_locator=None,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode=str(failure.get("extraction_mode") or "").strip() or None,
                model_alias=str(failure.get("model_alias") or "").strip() or None,
                estimated_input_tokens=None,
                failure_reason=blob or "proposition_extraction_failure",
                failure_type=ftype,
                repairable=is_repairable_error_text(blob),
                from_cache=False,
            )
        )

    for row in chunk_statuses:
        status = str(row.get("chunk_status") or "")
        if status not in {"failure", "failed"}:
            continue
        sid = str(row.get("source_record_id") or "").strip()
        if not sid:
            continue
        locator = str(row.get("fragment_locator") or "").strip() or None
        if _has_failure_for_locator(sid, locator):
            continue
        blob = str(row.get("error") or row.get("failure_reason") or "chunk_cache_failure")
        ftype = classify_extraction_failure_type(blob)
        frag_raw = row.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        ci = row.get("extraction_llm_chunk_index")
        idx = int(ci) if isinstance(ci, int) else None
        upsert(
            ExtractionFailureRecord(
                source_record_id=sid,
                source_title=str(row.get("source_title") or "").strip() or None,
                source_fragment_id=frag,
                fragment_locator=str(row.get("fragment_locator") or "").strip() or None,
                extraction_llm_chunk_index=idx,
                extraction_llm_chunk_total=None,
                extraction_mode=str(row.get("extraction_mode") or "").strip() or None,
                model_alias=str(row.get("model_alias") or "").strip() or None,
                estimated_input_tokens=None,
                failure_reason=blob,
                failure_type=ftype,
                repairable=is_repairable_error_text(blob) or ftype == "failed_chunk_cached",
                from_cache=True,
            )
        )

    return sorted(
        by_key.values(),
        key=lambda r: (r.source_record_id, r.fragment_locator or "", r.failure_type),
    )


def build_proposition_extraction_chunk_statuses(
    llm_traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive chunk-level cache / outcome rows from LLM diagnostic traces for export."""
    rows: list[dict[str, Any]] = []
    for trace in llm_traces:
        if not isinstance(trace, dict):
            continue
        cache_hit = trace.get("llm_cache_hit")
        skip = str(trace.get("skip_reason") or "")
        if cache_hit is None and skip not in {"failed_chunk_cached"}:
            if not _live_llm_call_attempted(trace):
                continue
        status = "live"
        error: str | None = None
        if _cached_llm_result_failed(trace):
            status = "failure"
            error = str(trace.get("model_error") or skip or "failed_chunk_cached")
        elif _cached_llm_result_successful(trace):
            status = "llm_success"
        elif _live_llm_call_failed(trace):
            status = "failure"
            error = str(trace.get("model_error") or "live_llm_call_failed")
        elif _live_llm_call_successful(trace):
            status = "llm_success"
        elif skip:
            status = "skipped"
            error = skip
        rows.append(
            {
                "source_record_id": trace.get("source_record_id"),
                "source_title": trace.get("source_title"),
                "source_fragment_id": trace.get("source_fragment_id"),
                "fragment_locator": trace.get("fragment_locator"),
                "extraction_llm_chunk_index": trace.get("extraction_llm_chunk_index"),
                "extraction_llm_chunk_total": trace.get("extraction_llm_chunk_total"),
                "model_alias": trace.get("model_alias"),
                "extraction_mode": trace.get("extraction_mode"),
                "estimated_input_tokens": trace.get("estimated_input_tokens"),
                "chunk_status": status,
                "from_cache": _trace_from_cache(trace),
                "llm_cache_hit": cache_hit,
                "skip_reason": skip or None,
                "error": error,
            }
        )
    return rows


def _top_counter_items(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def collect_raw_failure_examples(
    bundle: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Failed live LLM traces with safe raw-output excerpts for operator inspection."""
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    examples: list[dict[str, Any]] = []
    for row in llm_traces:
        if not _trace_failed(row) or _trace_from_cache(row):
            continue
        excerpt = str(row.get("raw_model_output_excerpt") or "").strip()
        if not excerpt and not row.get("failure_type") and not row.get("model_error"):
            continue
        examples.append(
            {
                "source_record_id": row.get("source_record_id"),
                "source_title": row.get("source_title"),
                "fragment_locator": row.get("fragment_locator"),
                "model_alias": row.get("model_alias"),
                "failure_type": row.get("failure_type")
                or classify_extraction_failure_type(
                    _failure_blob_from_trace(row),
                    explicit_failure_type=str(row.get("failure_type") or "") or None,
                ),
                "failure_reason": row.get("failure_reason") or row.get("model_error"),
                "finish_reason": row.get("finish_reason"),
                "prompt_template_id": row.get("prompt_template_id"),
                "prompt_hash": row.get("prompt_hash"),
                "prompt_version": row.get("prompt_version"),
                "estimated_input_tokens": row.get("estimated_input_tokens"),
                "raw_model_output_excerpt": excerpt or None,
                "raw_model_output_truncated": row.get("raw_model_output_truncated"),
                "candidate_row_count": row.get("candidate_row_count"),
                "accepted_row_count": row.get("accepted_row_count"),
            }
        )
        if len(examples) >= limit:
            break
    return examples


def summarize_extraction_jobs(
    bundle: dict[str, Any],
    *,
    raw_failure_example_limit: int = 0,
) -> dict[str, Any]:
    """Operator summary for inspect-extraction-jobs."""
    jobs = [
        row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)
    ]
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    job_metrics = compute_extraction_job_metrics(jobs)
    llm_metrics = merge_extraction_observability_metrics(jobs=jobs, llm_traces=llm_traces)
    failures = list_extraction_failure_records(bundle)
    props = bundle.get("propositions")
    n_props = len(props) if isinstance(props, list) else 0
    failed_examples = [
        {
            "source_record_id": f.source_record_id,
            "source_title": f.source_title,
            "fragment_locator": f.fragment_locator,
            "failure_type": f.failure_type,
            "failure_reason": f.failure_reason[:240],
            "model_alias": f.model_alias,
            "from_cache": f.from_cache,
            "estimated_input_tokens": f.estimated_input_tokens,
        }
        for f in failures[:20]
    ]
    return {
        "proposition_count": n_props,
        **job_metrics,
        **{k: llm_metrics[k] for k in llm_metrics if k.startswith(("live_", "cached_", "attempted_", "successful_", "failed_", "llm_results_"))},
        "failed_jobs_with_no_proposition": job_metrics["extraction_jobs_failed"],
        "failed_chunks_with_no_proposition": sum(
            1 for f in failures if f.extraction_llm_chunk_index is not None
        ),
        "failure_examples": failed_examples,
        **(
            {"raw_failure_examples": collect_raw_failure_examples(bundle, limit=raw_failure_example_limit)}
            if raw_failure_example_limit > 0
            else {}
        ),
    }


def summarize_extraction_inspection(bundle: dict[str, Any]) -> dict[str, Any]:
    """Aggregate stats for CLI inspect-extraction-failures."""
    traces: list[dict[str, Any]] = list(bundle.get("proposition_extraction_traces") or [])
    jobs = [
        row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)
    ]
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    failures = list_extraction_failure_records(bundle)
    repairable_chunks: list[RepairableExtractionChunk] = list_repairable_extraction_chunks(bundle)

    job_metrics = compute_extraction_job_metrics(jobs)
    llm_metrics = merge_extraction_observability_metrics(jobs=jobs, llm_traces=llm_traces)

    by_type: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_locator: Counter[str] = Counter()
    for record in failures:
        by_type[record.failure_type] += 1
        by_source[record.source_record_id] += 1
        loc_key = record.fragment_locator or f"{record.source_record_id}:full"
        by_locator[loc_key] += 1

    props = bundle.get("propositions")
    n_props = len(props) if isinstance(props, list) else 0

    frontier_llm_medium_high = sum(
        1
        for row in traces
        if isinstance(row, dict)
        and str(row.get("extraction_mode")) == "frontier"
        and str(row.get("extraction_method")) == "llm"
        and str(row.get("confidence") or "").lower() != "low"
    )
    frontier_fallback_traces = sum(
        1
        for row in traces
        if isinstance(row, dict)
        and str(row.get("extraction_mode")) == "frontier"
        and (row.get("extraction_method") == "fallback" or row.get("fallback_used"))
    )
    low_conf = sum(
        1 for row in traces if isinstance(row, dict) and str(row.get("confidence") or "").lower() == "low"
    )

    token_vals = [
        int(c.estimated_input_tokens)
        for c in repairable_chunks
        if isinstance(c.estimated_input_tokens, int) and int(c.estimated_input_tokens) > 0
    ]
    est_retry = sum(token_vals)
    estimated_retry_tokens: int | None = est_retry if token_vals else None

    repairable_records = [r for r in failures if r.repairable]
    has_repairable = bool(repairable_records or repairable_chunks)

    return {
        "proposition_count": n_props,
        "total_proposition_traces": len(traces),
        "successful_frontier_traces": frontier_llm_medium_high,
        "fallback_traces": frontier_fallback_traces,
        "low_confidence_traces": low_conf,
        **job_metrics,
        **{
            k: llm_metrics[k]
            for k in llm_metrics
            if k
            in {
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
            }
        },
        "failed_jobs_with_no_proposition": job_metrics["extraction_jobs_failed"],
        "failed_chunks_with_no_proposition": sum(
            1
            for f in failures
            if f.extraction_llm_chunk_index is not None or f.failure_type != "unknown"
        ),
        "extraction_failures_total": len(failures),
        "failure_reasons_by_type": dict(sorted(by_type.items())),
        "failure_reasons_by_source": dict(sorted(by_source.items())),
        "failure_reasons_by_locator": dict(sorted(by_locator.items())),
        "top_failed_sources": _top_counter_items(by_source),
        "top_failed_locators": _top_counter_items(by_locator),
        "repairable_chunks": len(repairable_chunks),
        "estimated_retry_token_count": est_retry if token_vals else None,
        "estimated_retry_tokens": estimated_retry_tokens,
        "affected_source_record_ids": sorted({f.source_record_id for f in failures}),
        "affected_source_fragments": sorted(
            {f"{f.source_record_id}:{f.source_fragment_id or 'full'}" for f in failures}
        ),
        "failure_reasons": sorted(by_type.keys()),
        "affected_proposition_ids": sorted(
            {pid for c in repairable_chunks for pid in c.affected_proposition_ids}
        ),
        "repairable_chunks_detail": [c.to_dict() for c in repairable_chunks],
        "failure_records": [r.to_dict() for r in failures[:50]],
        "has_repairable_extraction_failures": has_repairable,
    }
