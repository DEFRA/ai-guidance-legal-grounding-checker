"""Detect and summarize repairable frontier LLM extraction failures from exported bundles."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from .extract import parse_extraction_meta


# Substrings for model/infrastructure failures that may succeed after credits or config fix.
_REPAIRABLE_SUBSTRINGS: tuple[str, ...] = (
    "insufficient credit",
    "credit balance",
    "not enough credit",
    "quota",
    "rate limit",
    "ratelimit",
    "429",
    "context window",
    "context_window",
    "max token",
    "token limit",
    "model alias",
    "unknown model",
    "model not found",
    "json parse",
    "jsondecode",
    "model call or json parse failed",
    "model call failed",
    "llm call failure",
    "llm invocation",
    "overloaded",
    "api error",
)


def _blob_lower(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p is not None).lower()


def classify_repairable_failure_type(message: str) -> str | None:
    """Return coarse category when *message* suggests a retryable model/infra failure."""
    blob = message.lower()
    if not blob.strip():
        return None
    if "insufficient credit" in blob or "credit balance" in blob or "not enough credit" in blob:
        return "insufficient_credits"
    if "quota" in blob:
        return "quota"
    if "rate limit" in blob or "ratelimit" in blob or "429" in blob:
        return "rate_limit"
    if "context window" in blob or "context_window" in blob:
        return "context_window"
    if "model alias" in blob or "unknown model" in blob or "model not found" in blob:
        return "model_availability"
    if "json parse" in blob or "jsondecode" in blob or "model call or json parse failed" in blob:
        return "json_parse_or_llm_failure"
    if "schema validation" in blob or "validation failed" in blob:
        return "schema_validation_error"
    if "model returned no propositions" in blob or "returned no propositions" in blob:
        return "empty_model_response"
    if "provider returned no content" in blob:
        return "transport_empty_response"
    if "propositions=[]" in blob or "with propositions=[]" in blob:
        return "parsed_empty_proposition_list"
    if "non-json" in blob or "unparseable json" in blob:
        return "non_json_response"
    if "no extractable atoms" in blob:
        return "schema_valid_but_empty"
    if "validation removed all" in blob:
        return "post_filter_removed_all"
    if (
        "model call failed" in blob
        or "llm call failure" in blob
        or "llm invocation" in blob
        or "api error" in blob
        or "overloaded" in blob
    ):
        return "llm_call_failure"
    for sub in _REPAIRABLE_SUBSTRINGS:
        if sub in blob:
            return "other_model_infra"
    return None


def is_repairable_error_text(message: str | None) -> bool:
    return classify_repairable_failure_type(message or "") is not None


@dataclass(frozen=True)
class RepairableExtractionChunk:
    source_record_id: str
    source_snapshot_id: str | None
    source_fragment_id: str | None
    fragment_locator: str | None
    extraction_llm_chunk_index: int | None
    extraction_llm_chunk_total: int | None
    extraction_mode: str | None
    model_alias: str | None
    estimated_input_tokens: int | None
    fallback_used: bool | None
    failure_reason: str
    failure_type: str | None
    affected_proposition_ids: tuple[str, ...] = ()
    affected_trace_ids: tuple[str, ...] = ()

    def repair_job_key(self) -> tuple[str, str | None]:
        return (self.source_record_id, self.source_fragment_id)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}


def _gather_extraction_llm_traces(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("extraction_llm_call_traces")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    for row in bundle.get("stage_traces") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("stage_name")) != "proposition extraction":
            continue
        inp = row.get("inputs")
        if isinstance(inp, dict):
            inner = inp.get("extraction_llm_call_traces")
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def _trace_repair_blob(row: dict[str, Any]) -> str:
    return _blob_lower(
        row.get("skip_reason"),
        row.get("model_error"),
        row.get("failure_reason"),
        row.get("error"),
    )


def list_repairable_extraction_chunks(bundle: dict[str, Any]) -> list[RepairableExtractionChunk]:
    """Return structured repair targets (fragment- or chunk-scoped) from an in-memory bundle."""
    traces: list[dict[str, Any]] = list(bundle.get("proposition_extraction_traces") or [])
    propositions: list[dict[str, Any]] = list(bundle.get("propositions") or [])
    failures: list[dict[str, Any]] = list(bundle.get("proposition_extraction_failures") or [])
    llm_rows = _gather_extraction_llm_traces(bundle)

    by_key: dict[tuple[str, str | None, int | None], RepairableExtractionChunk] = {}

    def upsert(row: RepairableExtractionChunk) -> None:
        key = (row.source_record_id, row.source_fragment_id, row.extraction_llm_chunk_index)
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = row
            return
        by_key[key] = replace(
            cur,
            failure_reason=row.failure_reason
            if len(row.failure_reason) > len(cur.failure_reason)
            else cur.failure_reason,
            affected_proposition_ids=tuple(sorted(set(cur.affected_proposition_ids + row.affected_proposition_ids))),
            affected_trace_ids=tuple(sorted(set(cur.affected_trace_ids + row.affected_trace_ids))),
            estimated_input_tokens=row.estimated_input_tokens or cur.estimated_input_tokens,
        )

    # fail_closed records
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        sid = str(failure.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = failure.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        errs = failure.get("validation_errors")
        err_list = [str(x) for x in errs if str(x).strip()] if isinstance(errs, list) else []
        err_blob = _blob_lower(failure.get("failure_reason"), *err_list)
        ftype = classify_repairable_failure_type(err_blob)
        if ftype is None:
            continue
        upsert(
            RepairableExtractionChunk(
                source_record_id=sid,
                source_snapshot_id=None,
                source_fragment_id=frag,
                fragment_locator=None,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode=str(failure.get("extraction_mode") or "") or None,
                model_alias=str(failure.get("model_alias") or "") or None,
                estimated_input_tokens=None,
                fallback_used=None,
                failure_reason=err_blob or "proposition_extraction_failure",
                failure_type=ftype,
            )
        )

    # LLM diagnostic rows (live failures and cached failed chunks)
    for row in llm_rows:
        blob = _trace_repair_blob(row)
        ftype = classify_repairable_failure_type(blob)
        is_ctx_risk = (
            row.get("skipped_llm")
            and str(row.get("skip_reason") or "").lower() == "context_window_risk"
        )
        is_failed_chunk_cache = str(row.get("skip_reason") or "") == "failed_chunk_cached"
        live_failed = bool(row.get("model_error")) or row.get("llm_call_succeeded") is False
        if ftype is None and not is_ctx_risk and not is_failed_chunk_cache and not live_failed:
            continue
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
        est_i = int(est) if isinstance(est, int) and est > 0 else None
        loc = str(row.get("fragment_locator") or "").strip() or None
        resolved_ftype = ftype or ("context_window" if is_ctx_risk else "failed_chunk_cached" if is_failed_chunk_cache else "empty_model_response" if live_failed else None)
        if resolved_ftype is None:
            continue
        upsert(
            RepairableExtractionChunk(
                source_record_id=sid,
                source_snapshot_id=None,
                source_fragment_id=frag,
                fragment_locator=loc,
                extraction_llm_chunk_index=idx,
                extraction_llm_chunk_total=tot,
                extraction_mode=str(row.get("extraction_mode") or "") or None,
                model_alias=str(row.get("model_alias") or "") or None,
                estimated_input_tokens=est_i,
                fallback_used=None,
                failure_reason=blob or "extraction_llm_call_trace",
                failure_type=resolved_ftype,
            )
        )

    # Failed extraction jobs (local/frontier) with repairable or retry-worthy errors
    for job in bundle.get("proposition_extraction_jobs") or []:
        if not isinstance(job, dict) or not job.get("selected_for_extraction"):
            continue
        if int(job.get("proposition_count") or 0) > 0:
            continue
        err_parts: list[str] = []
        for key in ("errors", "warnings", "parse_error_message"):
            raw = job.get(key)
            if isinstance(raw, list):
                err_parts.extend(str(x) for x in raw if str(x).strip())
            elif raw is not None and str(raw).strip():
                err_parts.append(str(raw))
        err_blob = " ".join(err_parts)
        jtype = classify_repairable_failure_type(err_blob)
        if jtype is None and not job.get("repairable"):
            if not (job.get("llm_invoked") and int(job.get("proposition_count") or 0) == 0):
                continue
            jtype = "empty_model_response"
        sid = str(job.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = job.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        est = job.get("estimated_input_tokens")
        est_i = int(est) if isinstance(est, int) and est > 0 else None
        upsert(
            RepairableExtractionChunk(
                source_record_id=sid,
                source_snapshot_id=None,
                source_fragment_id=frag,
                fragment_locator=str(job.get("fragment_locator") or "").strip() or None,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode=str(job.get("extraction_mode") or "") or None,
                model_alias=str(job.get("model_alias") or "") or None,
                estimated_input_tokens=est_i,
                fallback_used=bool(job.get("fallback_used")),
                failure_reason=err_blob or "extraction_job_failed",
                failure_type=jtype,
            )
        )

    prop_by_id = {str(p.get("id")): p for p in propositions if isinstance(p, dict) and p.get("id")}

    for tr in traces:
        if not isinstance(tr, dict):
            continue
        ext_mode = str(tr.get("extraction_mode") or "").strip()
        method = str(tr.get("extraction_method") or "").strip()
        sig = tr.get("signals")
        sig_fb = bool(sig.get("fallback_used")) if isinstance(sig, dict) else False
        fb_tr = tr.get("fallback_used")
        fb = bool(fb_tr) if fb_tr is not None else sig_fb
        val_errs_raw = tr.get("validation_errors") or []
        val_errs = (
            [str(x) for x in val_errs_raw if str(x).strip()] if isinstance(val_errs_raw, list) else []
        )
        reason = str(tr.get("reason") or "").strip()
        err_tr = tr.get("errors") or []
        err_list2 = [str(x) for x in err_tr if str(x).strip()] if isinstance(err_tr, list) else []
        err_blob = _blob_lower(reason, *val_errs, *err_list2)

        pid = str(tr.get("proposition_id") or "").strip()
        if pid and pid in prop_by_id:
            meta = parse_extraction_meta(str(prop_by_id[pid].get("notes") or ""))
            if meta and bool(meta.get("fallback_used")) and str(meta.get("extraction_mode")) == "frontier":
                mve = meta.get("validation_errors") or []
                if isinstance(mve, list):
                    err_blob = _blob_lower(err_blob, *mve)

        is_frontier_fallback = ext_mode == "frontier" and (fb or method == "fallback")
        if not is_frontier_fallback:
            continue
        if classify_repairable_failure_type(err_blob) is None:
            continue

        sid = str(tr.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = tr.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        loc = str(tr.get("evidence_locator") or "").strip() or None
        est_from_sig: int | None = None
        if isinstance(sig, dict):
            raw_est = sig.get("estimated_input_tokens_max")
            if isinstance(raw_est, int):
                est_from_sig = raw_est
        tid = str(tr.get("id") or "").strip()
        upsert(
            RepairableExtractionChunk(
                source_record_id=sid,
                source_snapshot_id=str(tr.get("source_snapshot_id") or "").strip() or None,
                source_fragment_id=frag,
                fragment_locator=loc,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode=ext_mode or None,
                model_alias=str(tr.get("model_alias") or "").strip() or None,
                estimated_input_tokens=est_from_sig,
                fallback_used=fb,
                failure_reason=err_blob or reason or "frontier_fallback_trace",
                failure_type=classify_repairable_failure_type(err_blob),
                affected_proposition_ids=(pid,) if pid else (),
                affected_trace_ids=(tid,) if tid else (),
            )
        )

    # Proposition notes with judit_extraction_meta (fallback + repairable errors) when traces omit
    # fallback markers — common in mixed-quality / partial export views.
    for p in propositions:
        if not isinstance(p, dict):
            continue
        meta = parse_extraction_meta(str(p.get("notes") or ""))
        if not meta:
            continue
        if str(meta.get("extraction_mode") or "") != "frontier":
            continue
        if not bool(meta.get("fallback_used")):
            continue
        mve = meta.get("validation_errors") or []
        ve_list = (
            [str(x) for x in mve if str(x).strip()] if isinstance(mve, list) else []
        )
        err_blob = _blob_lower(*ve_list)
        if classify_repairable_failure_type(err_blob) is None:
            continue
        sid = str(p.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_raw = p.get("source_fragment_id")
        frag = str(frag_raw).strip() if frag_raw else None
        pid = str(p.get("id") or "").strip()
        upsert(
            RepairableExtractionChunk(
                source_record_id=sid,
                source_snapshot_id=str(p.get("source_snapshot_id") or "").strip() or None,
                source_fragment_id=frag,
                fragment_locator=None,
                extraction_llm_chunk_index=None,
                extraction_llm_chunk_total=None,
                extraction_mode="frontier",
                model_alias=None,
                estimated_input_tokens=None,
                fallback_used=True,
                failure_reason=err_blob or "proposition_notes_extraction_meta",
                failure_type=classify_repairable_failure_type(err_blob),
                affected_proposition_ids=(pid,) if pid else (),
                affected_trace_ids=(),
            )
        )

    return sorted(by_key.values(), key=lambda x: (x.source_record_id, x.source_fragment_id or "", x.failure_type or ""))


def repair_job_keys_from_chunks(chunks: Iterable[RepairableExtractionChunk]) -> set[tuple[str, str | None]]:
    return {c.repair_job_key() for c in chunks}


def summarize_extraction_inspection(bundle: dict[str, Any]) -> dict[str, Any]:
    """Aggregate stats for CLI / API inspect output."""
    from .extraction_inspection import summarize_extraction_inspection as _summarize

    return _summarize(bundle)


def repairable_extraction_metrics_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Normalized metrics shape for run_quality_summary.metrics.repairable_extraction."""
    scan = summarize_extraction_inspection(bundle)
    by_type = scan.get("failure_reasons_by_type") or {}
    est_raw = scan.get("estimated_retry_tokens")
    estimated_retry: int | None = int(est_raw) if isinstance(est_raw, int) else None
    return {
        "has_repairable_failures": bool(scan.get("has_repairable_extraction_failures")),
        "repairable_chunk_count": int(scan.get("repairable_chunks") or 0),
        "affected_proposition_count": len(scan.get("affected_proposition_ids") or []),
        "estimated_retry_tokens": estimated_retry,
        "failure_reasons": list(scan.get("failure_reasons") or []),
        # Backward-compatible: duplicate of estimated_retry_tokens (null when unknown).
        "estimated_retry_token_count": estimated_retry,
        "failure_reasons_by_type": by_type if isinstance(by_type, dict) else {},
    }


def _infer_case_inputs_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    stored = bundle.get("pipeline_case_inputs")
    if isinstance(stored, dict) and stored:
        return stored
    sources = bundle.get("source_records") or bundle.get("sources") or []
    jurisdictions: list[str] = []
    for s in sources:
        if isinstance(s, dict):
            j = str(s.get("jurisdiction") or "").strip()
            if j:
                jurisdictions.append(j)
    uniq = sorted(set(jurisdictions))
    comparison: dict[str, Any] = {"proposition_index": 0}
    if len(uniq) >= 2:
        comparison["jurisdiction_a"] = uniq[0]
        comparison["jurisdiction_b"] = uniq[1]
    run = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    wf = str(run.get("workflow_mode") or "auto").strip().lower()
    extraction: dict[str, Any] = {}
    scopes: list[str] = []
    for tr in bundle.get("proposition_extraction_traces") or []:
        if not isinstance(tr, dict):
            continue
        sig = tr.get("signals")
        if isinstance(sig, dict):
            fs = sig.get("focus_scopes")
            if isinstance(fs, list):
                scopes = [str(s).strip() for s in fs if str(s).strip()]
            if scopes:
                break
    if scopes:
        extraction["focus_scopes"] = scopes
    narrative = bundle.get("narrative") if isinstance(bundle.get("narrative"), dict) else {}
    return {
        "comparison": comparison,
        "narrative": narrative,
        "extraction": extraction,
        "prompts": {},
        "analysis_mode": "divergence" if wf == "divergence" else "auto",
        "strategy_versions": {"proposition_extraction": "v1"},
        "pipeline_version": "0.1.0",
    }


def build_case_data_for_repair(bundle: dict[str, Any], *, new_run_id: str | None = None) -> dict[str, Any]:
    topic = bundle.get("topic")
    clusters = bundle.get("clusters") or []
    cluster0 = (
        clusters[0]
        if isinstance(clusters, list) and clusters and isinstance(clusters[0], dict)
        else {"name": "", "description": ""}
    )
    inferred = _infer_case_inputs_from_bundle(bundle)
    run_existing = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    rid = new_run_id or str(run_existing.get("id") or "run-repair")
    case_data: dict[str, Any] = {
        "run_id": rid,
        "run_notes": str(run_existing.get("notes") or ""),
        "analysis_mode": inferred.get("analysis_mode", "auto"),
        "topic": topic if isinstance(topic, dict) else {"name": "", "subject_tags": [], "description": ""},
        "cluster": cluster0,
        "sources": bundle.get("source_records") or bundle.get("sources") or [],
        "comparison": inferred.get("comparison") or {},
        "narrative": inferred.get("narrative") or {},
        "extraction": dict(inferred.get("extraction") or {}),
        "prompts": inferred.get("prompts") or {},
        "strategy_versions": inferred.get("strategy_versions") or {},
        "pipeline_version": inferred.get("pipeline_version") or "0.1.0",
    }
    cx = inferred.get("extraction")
    if isinstance(cx, dict):
        extra = cx.get("model_error_policy")
        if isinstance(extra, str) and extra.strip():
            case_data["extraction"] = dict(case_data["extraction"])
            case_data["extraction"]["model_error_policy"] = extra.strip()
    return case_data


def run_cli_repair_pipeline(
    *,
    export_dir: Path,
    output_dir: Path | None,
    extraction_mode: str,
    extraction_fallback: str,
    only: Literal["repairable", "all"],
    in_place: bool,
    retry_failed_extraction_cache: bool | None,
    ignore_failed_extraction_cache: bool,
    retry_failed_llm: bool | None,
    source_cache_dir: str | None,
    derived_cache_dir: str | None,
    use_llm: bool,
    progress: Any | None,
) -> dict[str, Any]:
    """CLI entry — delegates to runner after loading the bundle from disk."""
    from .linting import load_exported_bundle
    from .runner import repair_extraction_from_export_dir

    root = Path(export_dir).expanduser()
    bundle = load_exported_bundle(root)
    if not in_place and output_dir is None:
        raise ValueError("--output-dir is required unless --in-place is set.")
    out_dir = Path(output_dir).expanduser() if not in_place else root

    run_json = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    base_run_id = str(run_json.get("id") or "run-unknown")
    new_run_id = base_run_id if in_place else f"{base_run_id}-repaired-{uuid.uuid4().hex[:8]}"

    return repair_extraction_from_export_dir(
        base_bundle=bundle,
        export_dir_abs=str(root.resolve()),
        output_export_dir=out_dir,
        new_run_id=new_run_id if not in_place else base_run_id,
        extraction_mode=extraction_mode,
        extraction_fallback=extraction_fallback,
        only=only,
        in_place=in_place,
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
        source_cache_dir=source_cache_dir,
        derived_cache_dir=derived_cache_dir,
        use_llm=use_llm,
        progress=progress,
    )
