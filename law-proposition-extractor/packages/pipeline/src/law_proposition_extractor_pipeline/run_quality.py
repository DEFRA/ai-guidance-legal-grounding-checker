import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from law_proposition_extractor_domain import RunArtifact, RunQualityGateResult, RunQualitySummary

from .cli_run_summary import (
    count_extraction_fallback_traces,
    extraction_mode_from_bundle,
    extraction_mode_requested_from_bundle,
)
from .extraction_llm_metrics import (
    compute_extraction_llm_trace_summary_metrics,
    extraction_llm_call_traces_from_bundle,
)
from .extraction_progress import extraction_timing_metrics_from_bundle
from .intake import content_hash
from .linting import lint_bundle

# (gate_id, display_name, error_substrings_in_order) — first matching gate wins.
_GATE_DEFINITIONS: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "run_artifacts",
        "Run artifact integrity",
        ("run_artifact missing content_hash",),
    ),
    (
        "proposition_extraction_traces",
        "Proposition extraction traces",
        (
            "extraction trace",
            "proposition missing extraction trace",
            "duplicate extraction trace",
        ),
    ),
    (
        "propositions",
        "Propositions",
        ("proposition ",),
    ),
    (
        "source_inventory",
        "Source inventory",
        ("source_inventory",),
    ),
    (
        "source_categorisation",
        "Source categorisation",
        ("source categorisation",),
    ),
    (
        "source_target_links",
        "Source target links",
        ("source target link",),
    ),
    (
        "source_fetch",
        "Source fetch",
        (
            "fetched source has no fetch",
            "successful fetch",
            "fetch/cache_hit",
            "source_fetch_metadata",
        ),
    ),
    (
        "source_snapshots",
        "Source snapshots",
        ("snapshot parser metadata",),
    ),
    (
        "source_fragments",
        "Source fragments",
        ("source fragment", "duplicate source fragment"),
    ),
    (
        "source_parse_traces",
        "Parse traces",
        ("parse trace",),
    ),
    (
        "divergence_observations",
        "Divergence observations",
        ("divergence observation",),
    ),
    (
        "content_lineage",
        "Content lineage",
        ("duplicate content_hash",),
    ),
    (
        "legacy_compatibility",
        "Legacy bundle compatibility",
        ("legacy bundle",),
    ),
    (
        "legal_scopes",
        "Legal scopes",
        ("proposition_scope_link", "invalid scope_id"),
    ),
]


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_len_list(bundle: dict[str, Any], key: str) -> int:
    value = bundle.get(key)
    return len(value) if isinstance(value, list) else 0


def _inventory_row_count(bundle: dict[str, Any]) -> int:
    inv = bundle.get("source_inventory")
    if not isinstance(inv, dict):
        return 0
    rows = inv.get("rows")
    return len(rows) if isinstance(rows, list) else 0


def _assign_gate(message: str) -> str:
    lower = message.lower()
    for gate_id, _name, needles in _GATE_DEFINITIONS:
        if any(needle in lower for needle in needles):
            return gate_id
    return "general"


def _extract_affected_id(message: str) -> str | None:
    """Best-effort id taken from lint messages (suffix after last ':')."""
    if ":" not in message:
        return None
    tail = message.rsplit(":", 1)[-1].strip()
    if not tail or tail.startswith("http"):
        return None
    inner = tail
    paren = re.search(r"\(([^)]+)\)\s*$", tail)
    if paren:
        inner = paren.group(1).strip()
    if re.match(r"^[\w\-]+$", inner):
        return inner
    if re.match(r"^[\w\-]+(?:\s+[\w\-]+)?$", inner) and " " not in inner.strip():
        return inner.strip()
    return tail if len(tail) <= 120 else None


def _gate_applicable(gate_id: str, bundle: dict[str, Any], propositions: list[Any]) -> bool:
    if gate_id == "proposition_extraction_traces":
        return bool(propositions)
    if gate_id == "divergence_observations":
        observations = bundle.get("divergence_observations")
        return isinstance(observations, list) and len(observations) > 0
    if gate_id == "legacy_compatibility":
        return bool(propositions)
    if gate_id == "legal_scopes":
        ls = bundle.get("legal_scopes")
        pl = bundle.get("proposition_scope_links")
        return (isinstance(ls, list) and len(ls) > 0) or (
            isinstance(pl, list) and len(pl) > 0
        )
    return True


def build_run_quality_summary(
    bundle: dict[str, Any],
    *,
    lint_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lint = lint_report if lint_report is not None else lint_bundle(bundle)
    errors: list[str] = list(lint.get("errors") or [])
    warnings: list[str] = list(lint.get("warnings") or [])
    run = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    run_id = str(run.get("id", "run-unknown"))

    sources = bundle.get("source_records")
    if not isinstance(sources, list):
        sources = bundle.get("sources")
    source_count = len(sources) if isinstance(sources, list) else 0

    propositions = bundle.get("propositions")
    if not isinstance(propositions, list):
        propositions = []

    divergence_assessments = bundle.get("divergence_assessments")
    div_count: int | None = None
    if isinstance(divergence_assessments, list) and len(divergence_assessments) > 0:
        div_count = len(divergence_assessments)

    err_by_gate: dict[str, list[str]] = {}
    warn_by_gate: dict[str, list[str]] = {}
    for msg in errors:
        err_by_gate.setdefault(_assign_gate(msg), []).append(msg)
    for msg in warnings:
        warn_by_gate.setdefault(_assign_gate(msg), []).append(msg)

    gate_results: list[RunQualityGateResult] = []
    gate_ids = [g[0] for g in _GATE_DEFINITIONS] + ["general"]
    for gate_id in gate_ids:
        name = next((n for gid, n, _ in _GATE_DEFINITIONS if gid == gate_id), "General")
        if gate_id == "general":
            name = "General"
        ge = err_by_gate.get(gate_id, [])
        gw = warn_by_gate.get(gate_id, [])
        affected: list[str] = []
        for msg in ge + gw:
            hint = _extract_affected_id(msg)
            if hint and hint not in affected:
                affected.append(hint)

        if not _gate_applicable(gate_id, bundle, propositions):
            gate_results.append(
                RunQualityGateResult(
                    gate_id=gate_id,
                    name=name,
                    status="skipped",
                    message="Not applicable for this run.",
                    error_count=0,
                    warning_count=0,
                    affected_artifact_ids=[],
                )
            )
            continue

        if ge:
            status = "fail"
            message = f"{len(ge)} error(s); first: {ge[0]}"
        elif gw:
            status = "warning"
            message = f"{len(gw)} warning(s); first: {gw[0]}"
        else:
            status = "pass"
            message = "OK"

        gate_results.append(
            RunQualityGateResult(
                gate_id=gate_id,
                name=name,
                status=status,
                message=message,
                error_count=len(ge),
                warning_count=len(gw),
                affected_artifact_ids=affected,
            )
        )

    ext_mode_effective = extraction_mode_from_bundle(bundle)
    ext_mode_requested = extraction_mode_requested_from_bundle(bundle)
    fallback_count = count_extraction_fallback_traces(bundle)
    extra_metrics: dict[str, Any] = {
        "extraction_mode_requested": ext_mode_requested,
        "extraction_mode_effective": ext_mode_effective,
        "fallback_count": fallback_count,
    }
    if ext_mode_effective in {"local", "frontier"}:
        from law_proposition_extractor_pipeline.extraction_llm_metrics import merge_extraction_observability_metrics

        jobs = bundle.get("proposition_extraction_jobs")
        job_rows = [row for row in jobs if isinstance(row, dict)] if isinstance(jobs, list) else []
        llm_metrics = merge_extraction_observability_metrics(
            jobs=job_rows,
            llm_traces=extraction_llm_call_traces_from_bundle(bundle),
        )
        llm_metrics["source_fragments_total"] = _safe_len_list(bundle, "source_fragments")
        llm_metrics.update(extraction_timing_metrics_from_bundle(bundle))
        extra_metrics.update(llm_metrics)

    overall_status: Literal["pass", "pass_with_warnings", "fail"]
    if lint.get("ok") and len(warnings) > 0:
        overall_status = "pass_with_warnings"
    elif lint.get("ok"):
        overall_status = "pass"
    else:
        overall_status = "fail"

    llm_extraction_failure_message: str | None = None
    if ext_mode_effective in {"local", "frontier"}:
        live_success = int(extra_metrics.get("live_llm_calls_successful") or 0)
        cached_success = int(extra_metrics.get("cached_llm_results_successful") or 0)
        any_llm_success = live_success + cached_success
        attempted = int(extra_metrics.get("live_llm_calls_attempted") or extra_metrics.get("attempted_llm_calls") or 0)
        if any_llm_success == 0 and fallback_count > 0:
            overall_status = "fail"
            llm_extraction_failure_message = "No successful LLM extraction occurred."
        elif len(propositions) == 0 and attempted == 0:
            selected_jobs = int(extra_metrics.get("extraction_jobs_selected") or 0)
            if not selected_jobs:
                pex_jobs = bundle.get("proposition_extraction_jobs")
                if isinstance(pex_jobs, list):
                    selected_jobs = sum(
                        1
                        for row in pex_jobs
                        if isinstance(row, dict) and row.get("selected_for_extraction")
                    )
            jobs_created = int(extra_metrics.get("extraction_jobs_created") or 0)
            if selected_jobs > 0:
                overall_status = "fail"
                skip_hist = extra_metrics.get("skip_reasons_by_type") or {}
                skip_hint = (
                    ", ".join(f"{k}={v}" for k, v in list(skip_hist.items())[:6])
                    if isinstance(skip_hist, dict) and skip_hist
                    else "see extraction_llm_call_traces"
                )
                from law_proposition_extractor_pipeline.cli_run_summary import derived_cache_dir_from_bundle
                from law_proposition_extractor_pipeline.llm_extraction_config import format_failed_chunk_cache_operator_hint

                derived_dir = derived_cache_dir_from_bundle(bundle)
                cache_hint = ""
                if isinstance(skip_hist, dict):
                    cache_hint = format_failed_chunk_cache_operator_hint(
                        derived_cache_dir=derived_dir,
                        skip_reasons_by_type=skip_hist,
                    )
                llm_extraction_failure_message = (
                    f"No LLM extraction calls were attempted for {selected_jobs} selected fragment job(s) "
                    f"({jobs_created} created, {extra_metrics.get('llm_extraction_skipped_count', 0)} skipped). "
                    f"Skip reasons: {skip_hint}."
                    + (f" {cache_hint}" if cache_hint else "")
                )
            elif jobs_created == 0 and int(extra_metrics.get("source_fragments_total") or 0) == 0:
                overall_status = "fail"
                llm_extraction_failure_message = (
                    "No extraction jobs were created (no source fragments and no extractable source text)."
                )
        elif len(propositions) == 0 and attempted > 0 and any_llm_success == 0:
            overall_status = "fail"
            llm_extraction_failure_message = (
                "LLM extraction was attempted but produced no valid propositions "
                f"({int(extra_metrics.get('failed_llm_calls') or 0)} failed call(s))."
            )

    recommendations: list[str] = []
    if llm_extraction_failure_message:
        recommendations.append(llm_extraction_failure_message)
    if not lint.get("ok"):
        failed = [g for g in gate_results if g.status == "fail"]
        if failed:
            recommendations.append(
                "Resolve failing gates: " + ", ".join(f"{g.gate_id}" for g in failed[:8])
            )
    if warnings:
        recommendations.append("Review lint warnings for data-quality and lineage completeness.")

    from law_proposition_extractor_pipeline.extraction_repair import repairable_extraction_metrics_from_bundle

    repair_metrics = repairable_extraction_metrics_from_bundle(bundle)

    summary = RunQualitySummary(
        run_id=run_id,
        generated_at=_utc_now_iso_z(),
        status=overall_status,
        source_count=source_count,
        snapshot_count=_safe_len_list(bundle, "source_snapshots"),
        fragment_count=_safe_len_list(bundle, "source_fragments"),
        proposition_count=len(propositions),
        divergence_assessment_count=div_count,
        fetch_attempt_count=_safe_len_list(bundle, "source_fetch_attempts"),
        parse_trace_count=_safe_len_list(bundle, "source_parse_traces"),
        proposition_extraction_trace_count=_safe_len_list(
            bundle, "proposition_extraction_traces"
        ),
        source_inventory_row_count=_inventory_row_count(bundle),
        source_target_link_count=_safe_len_list(bundle, "source_target_links"),
        source_categorisation_rationale_count=_safe_len_list(
            bundle, "source_categorisation_rationales"
        ),
        error_count=int(lint.get("error_count") or 0),
        warning_count=int(lint.get("warning_count") or 0),
        gate_results=gate_results,
        metrics={
            "lint_ok": bool(lint.get("ok")),
            "workflow_mode": bundle.get("workflow_mode")
            or run.get("workflow_mode"),
            "legal_scope_count": _safe_len_list(bundle, "legal_scopes"),
            "proposition_scope_link_count": _safe_len_list(bundle, "proposition_scope_links"),
            # Actionable scope-only lint (noise suppressed in lint_bundle for non-direct links).
            "legal_scope_warning_count": len(warn_by_gate.get("legal_scopes", [])),
            **extra_metrics,
            "repairable_extraction": {
                **repair_metrics,
            },
        },
        recommendations=recommendations,
    )
    return summary.model_dump(mode="json")


def attach_run_quality_summary(bundle: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    """Mutates bundle: adds run_quality_summary, flag, and run artifact. Idempotent unless force_refresh."""
    run_artifacts = bundle.get("run_artifacts")
    if not isinstance(run_artifacts, list):
        run_artifacts = []
        bundle["run_artifacts"] = run_artifacts
    existing = next(
        (
            a
            for a in run_artifacts
            if isinstance(a, dict) and str(a.get("artifact_type")) == "run_quality_summary"
        ),
        None,
    )
    if existing is not None and not force_refresh:
        return bundle["run_quality_summary"] if isinstance(bundle.get("run_quality_summary"), dict) else {}

    run = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    run_id = str(run.get("id", "run-unknown"))
    summary = build_run_quality_summary(bundle)
    payload = json.dumps(summary, sort_keys=True)
    bundle["run_quality_summary"] = summary
    bundle["has_run_quality_summary"] = True
    artifact = RunArtifact(
        id=f"artifact-{run_id}-run-quality-summary",
        run_id=run_id,
        artifact_type="run_quality_summary",
        provenance="pipeline.export",
        content_hash=content_hash(payload),
        metadata={},
    ).model_dump(mode="json")
    if existing is not None:
        existing.update(artifact)
    else:
        run_artifacts.append(artifact)
    return summary
