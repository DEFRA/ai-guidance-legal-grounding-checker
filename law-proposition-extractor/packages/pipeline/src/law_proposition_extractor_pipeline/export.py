from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import (
    Cluster,
    ComparisonRun,
    DivergenceAssessment,
    DivergenceFinding,
    DivergenceObservation,
    LegalScope,
    LegalScopeReviewCandidate,
    NarrativeExport,
    Proposition,
    PropositionExtractionTrace,
    PropositionScopeLink,
    ReviewDecision,
    RunArtifact,
    SourceFamilyCandidate,
    SourceFragment,
    SourceParseTrace,
    SourceRecord,
    SourceSnapshot,
    Topic,
)
from law_proposition_extractor_exporters import export_static_bundle

from .pipeline_reviews import attach_pipeline_review_decisions_artifact
from .proposition_dataset import attach_proposition_dataset_metadata
from .proposition_quality_gates import (
    run_proposition_quality_gates,
    write_normalisation_quality_artifacts,
)
from .run_model_md import (
    MODEL_MD_FILENAME,
    attach_run_model_metadata,
    load_case_data_for_run,
    render_model_md,
)
from .run_quality import attach_run_quality_summary


def attach_proposition_normalisation_quality(
    bundle: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Run normalisation quality gates and persist JSON (and summary markdown) on export."""
    propositions = bundle.get("propositions")
    if not isinstance(propositions, list) or not propositions:
        return None
    report = run_proposition_quality_gates(propositions, newly_normalised=True)
    payload = report.to_dict()
    bundle["proposition_normalisation_quality"] = payload
    if output_dir is not None:
        write_normalisation_quality_artifacts(output_dir, report)
    return payload


def build_bundle(
    *,
    topic: Topic,
    clusters: list[Cluster],
    run: ComparisonRun,
    sources: list[SourceRecord],
    source_fetch_metadata: list[Any] | None = None,
    source_fetch_attempts: list[dict[str, Any]] | None = None,
    source_target_links: list[dict[str, Any]] | None = None,
    source_inventory: dict[str, Any] | None = None,
    source_categorisation_rationales: list[dict[str, Any]] | None = None,
    source_snapshots: list[SourceSnapshot] | None = None,
    source_fragments: list[SourceFragment] | None = None,
    source_parse_traces: list[SourceParseTrace] | None = None,
    proposition_extraction_traces: list[PropositionExtractionTrace] | None = None,
    proposition_extraction_jobs: list[dict[str, Any]] | None = None,
    proposition_extraction_failures: list[dict[str, Any]] | None = None,
    proposition_completeness_assessments: list[Any] | None = None,
    propositions: list[Proposition],
    proposition_inventory: dict[str, Any] | None = None,
    divergence_assessments: list[DivergenceAssessment],
    divergence_findings: list[DivergenceFinding] | None = None,
    divergence_observations: list[DivergenceObservation] | None = None,
    review_decisions: list[ReviewDecision] | None = None,
    pipeline_review_decisions: list[dict[str, Any]] | None = None,
    run_artifacts: list[RunArtifact] | None = None,
    source_family_candidates: list[dict[str, Any]] | None = None,
    narrative: NarrativeExport,
    legal_scopes: list[LegalScope] | None = None,
    proposition_scope_links: list[PropositionScopeLink] | None = None,
    scope_inventory: dict[str, Any] | None = None,
    scope_review_candidates: list[LegalScopeReviewCandidate] | None = None,
) -> dict[str, Any]:
    source_snapshots = source_snapshots or []
    source_fragments = source_fragments or []
    source_parse_traces = source_parse_traces or []
    proposition_extraction_traces = proposition_extraction_traces or []
    proposition_extraction_jobs = proposition_extraction_jobs or []
    proposition_extraction_failures = proposition_extraction_failures or []
    source_fetch_metadata = source_fetch_metadata or []
    normalized_source_fetch_metadata: list[dict[str, Any]] = []
    for item in source_fetch_metadata:
        if isinstance(item, dict):
            normalized_source_fetch_metadata.append(item)
            continue
        if hasattr(item, "model_dump"):
            normalized_source_fetch_metadata.append(item.model_dump(mode="json"))
    source_inventory = source_inventory or {}
    source_fetch_attempts = source_fetch_attempts or []
    source_target_links = source_target_links or []
    source_categorisation_rationales = source_categorisation_rationales or []
    proposition_inventory = proposition_inventory or {}
    divergence_observations = divergence_observations or [
        DivergenceObservation.model_validate(item.model_dump(mode="json"))
        for item in divergence_assessments
    ]
    divergence_findings = divergence_findings or []
    review_decisions = review_decisions or []
    pipeline_review_decisions = pipeline_review_decisions or []
    run_artifacts = run_artifacts or []
    legal_scopes = legal_scopes or []
    proposition_scope_links = proposition_scope_links or []
    scope_inventory = scope_inventory or {}
    scope_review_candidates = scope_review_candidates or []
    proposition_completeness_assessments = proposition_completeness_assessments or []
    completeness_dumped: list[dict[str, Any]] = []
    for item in proposition_completeness_assessments:
        if isinstance(item, dict):
            completeness_dumped.append(item)
        elif hasattr(item, "model_dump"):
            completeness_dumped.append(item.model_dump(mode="json"))
        else:
            completeness_dumped.append(dict(item))

    sf_input = source_family_candidates or []
    normalized_source_family_candidates: list[dict[str, Any]] = []
    for item in sf_input:
        if hasattr(item, "model_dump"):
            normalized_source_family_candidates.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            normalized_source_family_candidates.append(
                SourceFamilyCandidate.model_validate(item).model_dump(mode="json")
            )

    return {
        "workflow_mode": run.workflow_mode,
        "has_divergence_outputs": bool(divergence_assessments),
        "topic": topic.model_dump(mode="json"),
        "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
        "run": run.model_dump(mode="json"),
        "source_records": [source.model_dump(mode="json") for source in sources],
        "source_fetch_metadata": normalized_source_fetch_metadata,
        "source_fetch_attempts": source_fetch_attempts,
        "source_target_links": source_target_links,
        "source_inventory": source_inventory,
        "source_categorisation_rationales": source_categorisation_rationales,
        "source_snapshots": [snapshot.model_dump(mode="json") for snapshot in source_snapshots],
        "source_fragments": [fragment.model_dump(mode="json") for fragment in source_fragments],
        "source_parse_traces": [
            parse_trace.model_dump(mode="json") for parse_trace in source_parse_traces
        ],
        "proposition_extraction_traces": [
            item.model_dump(mode="json") for item in proposition_extraction_traces
        ],
        "has_proposition_extraction_traces": bool(proposition_extraction_traces),
        "proposition_extraction_trace_count": len(proposition_extraction_traces),
        "proposition_extraction_jobs": proposition_extraction_jobs,
        "has_proposition_extraction_jobs": bool(proposition_extraction_jobs),
        "proposition_extraction_job_count": len(proposition_extraction_jobs),
        "proposition_extraction_failures": proposition_extraction_failures,
        "has_proposition_extraction_failures": bool(proposition_extraction_failures),
        "proposition_completeness_assessments": completeness_dumped,
        "has_proposition_completeness_assessments": bool(completeness_dumped),
        "proposition_completeness_assessment_count": len(completeness_dumped),
        "sources": [source.model_dump(mode="json") for source in sources],
        "proposition_inventory": proposition_inventory,
        "propositions": [prop.model_dump(mode="json") for prop in propositions],
        # Canonical new shape.
        "divergence_findings": [item.model_dump(mode="json") for item in divergence_findings],
        "divergence_observations": [
            item.model_dump(mode="json") for item in divergence_observations
        ],
        # Legacy compatibility export.
        "divergence_assessments": [item.model_dump(mode="json") for item in divergence_assessments],
        "review_decisions": [item.model_dump(mode="json") for item in review_decisions],
        "pipeline_review_decisions": list(pipeline_review_decisions),
        "run_artifacts": [item.model_dump(mode="json") for item in run_artifacts],
        "source_family_candidates": normalized_source_family_candidates,
        "has_source_family_candidates": bool(normalized_source_family_candidates),
        "source_family_candidate_count": len(normalized_source_family_candidates),
        "narrative": narrative.model_dump(mode="json"),
        "legal_scopes": [item.model_dump(mode="json") for item in legal_scopes],
        "proposition_scope_links": [
            item.model_dump(mode="json") for item in proposition_scope_links
        ],
        "scope_inventory": scope_inventory,
        "scope_review_candidates": [
            item.model_dump(mode="json") for item in scope_review_candidates
        ],
        "has_legal_scopes": bool(legal_scopes),
        "has_proposition_scope_links": bool(proposition_scope_links),
        "has_scope_inventory": bool(scope_inventory),
        "legal_scope_count": len(legal_scopes),
        "proposition_scope_link_count": len(proposition_scope_links),
    }


def export_bundle(
    bundle: dict[str, Any],
    output_dir: str = "dist/static-report",
    *,
    case_data: dict[str, Any] | None = None,
    run_path: str | None = None,
) -> None:
    refresh_extraction_observability_in_bundle(bundle)
    attach_run_quality_summary(bundle, force_refresh=True)
    attach_proposition_normalisation_quality(bundle, output_dir=output_dir)
    attach_proposition_dataset_metadata(bundle)
    attach_pipeline_review_decisions_artifact(bundle)
    from .effective_law import attach_effective_law_artifacts

    attach_effective_law_artifacts(bundle)
    from .source_legal_effects import attach_source_legal_effects

    attach_source_legal_effects(bundle)
    from .heuristics.provenance_attach import (
        attach_provenance_and_source_effect_explanations,
    )

    attach_provenance_and_source_effect_explanations(bundle)
    from .heuristics.selection_explanations import attach_decision_explanations

    attach_decision_explanations(bundle)
    _attach_export_run_metadata(bundle)
    resolved_case = case_data if case_data is not None else load_case_data_for_run(run_path, bundle)
    attach_run_model_metadata(
        bundle,
        case_data=resolved_case,
        output_dir=output_dir,
        output_path_anchor=Path(output_dir).resolve(),
    )
    export_static_bundle(bundle, output_dir=output_dir)
    from .evaluation import write_run_evaluation_after_export

    write_run_evaluation_after_export(output_dir, bundle)
    meta = bundle.get("run_model_metadata")
    if isinstance(meta, dict):
        Path(output_dir).joinpath(MODEL_MD_FILENAME).write_text(
            render_model_md(meta),
            encoding="utf-8",
        )


def refresh_extraction_observability_in_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Recompute extraction job / LLM metrics and chunk statuses from persisted artifacts."""
    from .extraction_inspection import (
        build_proposition_extraction_chunk_statuses,
        summarize_extraction_inspection,
    )
    from .extraction_llm_metrics import (
        extraction_llm_call_traces_from_bundle,
        merge_extraction_observability_metrics,
    )

    jobs = [
        row for row in (bundle.get("proposition_extraction_jobs") or []) if isinstance(row, dict)
    ]
    llm_traces = extraction_llm_call_traces_from_bundle(bundle)
    if llm_traces:
        bundle["extraction_llm_call_traces"] = llm_traces
    bundle["proposition_extraction_chunk_statuses"] = build_proposition_extraction_chunk_statuses(
        llm_traces
    )
    metrics = merge_extraction_observability_metrics(jobs=jobs, llm_traces=llm_traces)
    inspection = summarize_extraction_inspection(bundle)
    bundle["extraction_inspection_summary"] = {
        k: inspection[k]
        for k in inspection
        if k not in {"failure_records", "repairable_chunks_detail"}
    }
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("stage_name") or "") != "proposition extraction":
            continue
        inputs = tr.setdefault("inputs", {})
        if isinstance(inputs, dict):
            inputs.update({k: metrics[k] for k in metrics if k not in inputs})
            inputs["extraction_llm_call_traces"] = llm_traces
        outputs = tr.setdefault("outputs", {})
        if isinstance(outputs, dict):
            for key in (
                "extraction_jobs_total",
                "extraction_jobs_failed",
                "live_llm_calls_attempted",
                "live_llm_calls_successful",
                "live_llm_calls_failed",
                "cached_llm_results_successful",
                "cached_llm_results_failed",
            ):
                if key in metrics:
                    outputs[key] = metrics[key]
        break
    existing_quality = bundle.get("run_quality_summary")
    if isinstance(existing_quality, dict):
        existing_metrics = existing_quality.get("metrics")
        if isinstance(existing_metrics, dict):
            existing_metrics.update(metrics)
    return metrics


def _attach_export_run_metadata(bundle: dict[str, Any]) -> None:
    from .cli_run_summary import build_cli_completion_summary
    from .run_quality import build_run_quality_summary

    quality = bundle.get("run_quality_summary")
    if not isinstance(quality, dict):
        quality = build_run_quality_summary(bundle)
        bundle["run_quality_summary"] = quality
    summary = build_cli_completion_summary(bundle, quality_summary=quality, output_dir=None)
    bundle["export_run_metadata"] = {
        "extraction_mode_requested": summary.get("extraction_mode_requested"),
        "extraction_mode_effective": summary.get("extraction_mode_effective"),
        "proposition_count": summary.get("propositions"),
        "attempted_llm_calls": summary.get("attempted_llm_calls"),
        "successful_llm_calls": summary.get("successful_llm_calls"),
        "failed_llm_calls": summary.get("failed_llm_calls"),
        "live_llm_calls_attempted": summary.get("live_llm_calls_attempted"),
        "live_llm_calls_successful": summary.get("live_llm_calls_successful"),
        "live_llm_calls_failed": summary.get("live_llm_calls_failed"),
        "cached_llm_results_successful": summary.get("cached_llm_results_successful"),
        "cached_llm_results_failed": summary.get("cached_llm_results_failed"),
        "cached_successful_llm_results": summary.get("cached_successful_llm_results"),
        "cached_failed_llm_results": summary.get("cached_failed_llm_results"),
        "llm_results_reused_from_cache": summary.get("llm_results_reused_from_cache"),
        "fallback_count": summary.get("fallback_count"),
    }
