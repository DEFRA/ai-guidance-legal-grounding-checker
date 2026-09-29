import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    compact = "-".join(segment for segment in normalized.split("-") if segment)
    return compact or "item"


def _proposition_completeness_counts(bundle: dict[str, Any]) -> dict[str, int]:
    rows = bundle.get("proposition_completeness_assessments")
    if not isinstance(rows, list):
        return {"complete": 0, "context_dependent": 0, "fragmentary": 0}
    counts = {"complete": 0, "context_dependent": 0, "fragmentary": 0}
    for row in rows:
        if not isinstance(row, dict):
            continue
        st = str(row.get("status", "")).strip()
        if st in counts:
            counts[st] += 1
    return counts


def _artifact_payload(bundle: dict[str, Any], artifact_type: str) -> Any:
    payload_by_type = {
        "source_records": bundle.get("source_records", bundle.get("sources", [])),
        "source_fetch_metadata": bundle.get("source_fetch_metadata", []),
        "source_fetch_attempts": bundle.get("source_fetch_attempts", []),
        "source_target_links": bundle.get("source_target_links", []),
        "source_inventory": bundle.get("source_inventory", {}),
        "source_categorisation_rationales": bundle.get("source_categorisation_rationales", []),
        "source_snapshots": bundle.get("source_snapshots", []),
        "source_fragments": bundle.get("source_fragments", []),
        "source_parse_traces": bundle.get("source_parse_traces", []),
        "proposition_extraction_traces": bundle.get("proposition_extraction_traces", []),
        "proposition_extraction_jobs": bundle.get("proposition_extraction_jobs", []),
        "propositions": bundle.get("propositions", []),
        "proposition_completeness_assessments": bundle.get("proposition_completeness_assessments", []),
        "divergence_assessments": bundle.get("divergence_assessments", []),
        "divergence_observations": bundle.get("divergence_observations", []),
        "divergence_findings": bundle.get("divergence_findings", []),
        "proposition_inventory": bundle.get("proposition_inventory", {}),
        "narrative_export": bundle.get("narrative", {}),
        "review_decisions": bundle.get("review_decisions", []),
        "pipeline_review_decisions": bundle.get("pipeline_review_decisions", []),
        "run": bundle.get("run", {}),
        "run_quality_summary": bundle.get("run_quality_summary"),
        "legal_scopes": bundle.get("legal_scopes", []),
        "proposition_scope_links": bundle.get("proposition_scope_links", []),
        "scope_inventory": bundle.get("scope_inventory", {}),
        "scope_review_candidates": bundle.get("scope_review_candidates", []),
        "source_family_candidates": bundle.get("source_family_candidates", []),
        "proposition_relationships": bundle.get("proposition_relationships", {}),
        "effective_law_statements": bundle.get("effective_law_statements", {}),
        "proposition_matcher_law_candidates": bundle.get("proposition_matcher_law_candidates", {}),
        "legal_rule_groups": bundle.get("legal_rule_groups", {}),
        "legal_rule_relationships": bundle.get("legal_rule_relationships", {}),
        "source_legal_effects": bundle.get("source_legal_effects", {}),
        "decision_explanations": bundle.get("decision_explanations", {}),
    }
    return payload_by_type.get(
        artifact_type,
        {
            "artifact_type": artifact_type,
            "note": "No direct artifact payload mapping available.",
        },
    )


def _normalize_trace(trace: dict[str, Any], run_id: str) -> dict[str, Any]:
    normalized = dict(trace)
    normalized.setdefault("stage_name", "unknown")
    normalized.setdefault("run_id", run_id)
    normalized.setdefault("timestamp", _utc_now_iso())
    normalized.setdefault("inputs", {})
    normalized.setdefault("outputs", {})
    normalized.setdefault("strategy_used", "unknown")
    normalized.setdefault("model_alias_used", None)
    normalized.setdefault("duration_ms", 0)
    normalized.setdefault("warnings", [])
    normalized.setdefault("errors", [])
    return normalized


def _write_stage_traces(
    *,
    bundle: dict[str, Any],
    run_id: str,
    run_dir: Path,
    root: Path,
    final_export_timestamp: str,
    final_export_duration_ms: int,
) -> list[dict[str, Any]]:
    stage_traces = bundle.get("stage_traces")
    if not isinstance(stage_traces, list):
        stage_traces = []
        bundle["stage_traces"] = stage_traces

    stage_traces.append(
        {
            "stage_name": "final export",
            "run_id": run_id,
            "timestamp": final_export_timestamp,
            "inputs": {
                "output_dir": str(root),
                "root_manifest": "manifest.json",
                "run_manifest": f"runs/{run_id}/manifest.json",
            },
            "outputs": {
                "run_dir": f"runs/{run_id}",
                "artifact_dir": f"runs/{run_id}/artifacts",
            },
            "strategy_used": "static_bundle_file_export",
            "model_alias_used": None,
            "duration_ms": max(0, final_export_duration_ms),
            "warnings": [],
            "errors": [],
        }
    )

    traces_dir = run_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    index_entries: list[dict[str, Any]] = []
    for idx, raw_trace in enumerate(stage_traces, start=1):
        trace = _normalize_trace(raw_trace if isinstance(raw_trace, dict) else {}, run_id)
        trace_filename = f"{idx:02d}-{_slug(str(trace['stage_name']))}.json"
        trace_file = traces_dir / trace_filename
        _write_json(trace_file, trace)
        storage_uri = str(trace_file.relative_to(root))
        index_entries.append(
            {
                "order": idx,
                "stage_name": trace["stage_name"],
                "storage_uri": storage_uri,
            }
        )
    return index_entries


def _write_run_artifacts(
    bundle: dict[str, Any],
    root: Path,
    *,
    final_export_timestamp: str,
    final_export_duration_ms: int,
) -> None:
    run = bundle.get("run", {})
    run_id = str(run.get("id", "run-unknown"))
    run_dir = root / "runs" / _slug(run_id)
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "run.json", run)

    run_artifacts = bundle.get("run_artifacts")
    if not isinstance(run_artifacts, list):
        run_artifacts = []
        bundle["run_artifacts"] = run_artifacts

    if not run_artifacts:
        run_artifacts.extend(
            [
                {
                    "id": f"artifact-{run_id}-assessments",
                    "run_id": run_id,
                    "artifact_type": "divergence_assessments",
                    "provenance": "pipeline.compare",
                    "content_hash": "not-computed",
                },
                {
                    "id": f"artifact-{run_id}-narrative",
                    "run_id": run_id,
                    "artifact_type": "narrative_export",
                    "provenance": "pipeline.export",
                    "content_hash": "not-computed",
                },
            ]
        )

    for artifact in run_artifacts:
        artifact_id = str(
            artifact.get(
                "id",
                f"artifact-{run_id}-{artifact.get('artifact_type', 'unknown')}",
            )
        )
        artifact_type = str(artifact.get("artifact_type", "unknown"))
        artifact_file = artifacts_dir / f"{_slug(artifact_id)}.json"
        _write_json(artifact_file, _artifact_payload(bundle, artifact_type))
        artifact["storage_uri"] = str(artifact_file.relative_to(root))
    _write_json(run_dir / "run-artifacts.json", run_artifacts)

    stage_index = _write_stage_traces(
        bundle=bundle,
        run_id=run_id,
        run_dir=run_dir,
        root=root,
        final_export_timestamp=final_export_timestamp,
        final_export_duration_ms=final_export_duration_ms,
    )
    _write_json(
        run_dir / "trace-manifest.json",
        {
            "run_id": run_id,
            "stage_count": len(stage_index),
            "stages": stage_index,
        },
    )

    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "workflow_mode": run.get("workflow_mode"),
            "proposition_count": len(bundle.get("propositions", [])),
            "divergence_assessment_count": len(bundle.get("divergence_assessments", [])),
            "source_fetch_attempt_count": len(bundle.get("source_fetch_attempts", [])),
            "source_parse_trace_count": len(bundle.get("source_parse_traces", [])),
            "source_fragment_count": len(bundle.get("source_fragments", [])),
            "proposition_extraction_trace_count": len(bundle.get("proposition_extraction_traces", [])),
            "has_proposition_extraction_jobs": bool(bundle.get("proposition_extraction_jobs", [])),
            "proposition_extraction_job_count": len(bundle.get("proposition_extraction_jobs", [])),
            "proposition_completeness_assessment_count": len(
                bundle.get("proposition_completeness_assessments", []) or []
            ),
            "has_proposition_completeness_assessments": bool(
                bundle.get("proposition_completeness_assessments", [])
            ),
            "proposition_completeness_status_counts": _proposition_completeness_counts(bundle),
            "source_target_link_count": len(bundle.get("source_target_links", [])),
            "source_categorisation_rationale_count": len(
                bundle.get("source_categorisation_rationales", [])
            ),
            "has_run_quality_summary": isinstance(bundle.get("run_quality_summary"), dict),
            "has_pipeline_review_decisions": bool(bundle.get("pipeline_review_decisions")),
            "pipeline_review_decision_count": len(bundle.get("pipeline_review_decisions", []) or []),
            "has_legal_scopes": bool(bundle.get("legal_scopes")),
            "has_proposition_scope_links": bool(bundle.get("proposition_scope_links")),
            "has_scope_inventory": bool(bundle.get("scope_inventory")),
            "legal_scope_count": len(bundle.get("legal_scopes", []) or []),
            "proposition_scope_link_count": len(bundle.get("proposition_scope_links", []) or []),
            "scope_review_candidate_count": len(bundle.get("scope_review_candidates", []) or []),
            "source_family_candidate_count": len(bundle.get("source_family_candidates", []) or []),
            "has_source_family_candidates": bool(bundle.get("source_family_candidates", [])),
            "artifact_count": len(run_artifacts),
            "stage_trace_count": len(stage_index),
            "trace_manifest_uri": str((run_dir / "trace-manifest.json").relative_to(root)),
            "artifacts": [
                {
                    "id": artifact.get("id"),
                    "artifact_type": artifact.get("artifact_type"),
                    "storage_uri": artifact.get("storage_uri"),
                }
                for artifact in run_artifacts
            ],
        },
    )


def _export_manifest_run_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    meta = bundle.get("export_run_metadata")
    if isinstance(meta, dict):
        return {
            "extraction_mode_requested": meta.get("extraction_mode_requested"),
            "extraction_mode_effective": meta.get("extraction_mode_effective"),
            "proposition_count": meta.get("proposition_count"),
            "attempted_llm_calls": meta.get("attempted_llm_calls"),
            "successful_llm_calls": meta.get("successful_llm_calls"),
            "failed_llm_calls": meta.get("failed_llm_calls"),
            "live_llm_calls_attempted": meta.get("live_llm_calls_attempted"),
            "live_llm_calls_successful": meta.get("live_llm_calls_successful"),
            "live_llm_calls_failed": meta.get("live_llm_calls_failed"),
            "cached_llm_results_successful": meta.get("cached_llm_results_successful"),
            "cached_llm_results_failed": meta.get("cached_llm_results_failed"),
            "cached_successful_llm_results": meta.get("cached_successful_llm_results"),
            "cached_failed_llm_results": meta.get("cached_failed_llm_results"),
            "llm_results_reused_from_cache": meta.get("llm_results_reused_from_cache"),
            "fallback_count": meta.get("fallback_count"),
        }
    quality = bundle.get("run_quality_summary")
    if isinstance(quality, dict):
        return {
            "extraction_mode_requested": quality.get("extraction_mode_requested"),
            "extraction_mode_effective": quality.get("extraction_mode_effective"),
            "proposition_count": quality.get("proposition_count"),
        }
    props = bundle.get("propositions")
    return {
        "proposition_count": len(props) if isinstance(props, list) else 0,
    }


def export_static_bundle(bundle: dict[str, Any], output_dir: str) -> None:
    export_started_at = perf_counter()
    export_timestamp = _utc_now_iso()
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    _write_json(
        root / "manifest.json",
        {
            "app": "Law Proposition Extractor",
            "version": "0.1.0",
            "bundle_type": "static-report",
            "workflow_mode": bundle.get(
                "workflow_mode",
                bundle.get("run", {}).get("workflow_mode"),
            ),
            "has_divergence_outputs": bundle.get(
                "has_divergence_outputs",
                bool(bundle.get("divergence_assessments", [])),
            ),
            "has_topic": "topic" in bundle,
            "has_clusters": "clusters" in bundle,
            "has_source_categorisation_rationales": bool(
                bundle.get("source_categorisation_rationales", [])
            ),
            "has_source_target_links": bool(bundle.get("source_target_links", [])),
            "has_source_fetch_attempts": bool(bundle.get("source_fetch_attempts", [])),
            "has_source_parse_traces": bool(bundle.get("source_parse_traces", [])),
            "source_parse_trace_count": len(bundle.get("source_parse_traces", [])),
            "source_fragment_count": len(bundle.get("source_fragments", [])),
            "has_proposition_extraction_traces": bool(bundle.get("proposition_extraction_traces", [])),
            "proposition_extraction_trace_count": len(bundle.get("proposition_extraction_traces", [])),
            "has_proposition_extraction_jobs": bool(bundle.get("proposition_extraction_jobs", [])),
            "proposition_extraction_job_count": len(bundle.get("proposition_extraction_jobs", [])),
            "has_proposition_completeness_assessments": bool(
                bundle.get("proposition_completeness_assessments", [])
            ),
            "proposition_completeness_assessment_count": len(
                bundle.get("proposition_completeness_assessments", []) or []
            ),
            "proposition_completeness_status_counts": _proposition_completeness_counts(bundle),
            "has_run_quality_summary": isinstance(bundle.get("run_quality_summary"), dict),
            "has_pipeline_review_decisions": bool(bundle.get("pipeline_review_decisions")),
            "pipeline_review_decision_count": len(bundle.get("pipeline_review_decisions", []) or []),
            "has_legal_scopes": bool(bundle.get("legal_scopes")),
            "has_proposition_scope_links": bool(bundle.get("proposition_scope_links")),
            "has_scope_inventory": bool(bundle.get("scope_inventory")),
            "legal_scope_count": len(bundle.get("legal_scopes", []) or []),
            "proposition_scope_link_count": len(bundle.get("proposition_scope_links", []) or []),
            "scope_review_candidate_count": len(bundle.get("scope_review_candidates", []) or []),
            "has_source_family_candidates": bool(bundle.get("source_family_candidates", [])),
            "source_family_candidate_count": len(bundle.get("source_family_candidates", []) or []),
            **_export_manifest_run_metadata(bundle),
        },
    )
    _write_json(root / "topic.json", bundle["topic"])
    _write_json(root / "clusters.json", bundle["clusters"])
    _write_json(root / "run.json", bundle["run"])
    sources_payload = bundle.get("source_records", bundle.get("sources", []))
    _write_json(root / "sources.json", sources_payload)
    _write_json(root / "source_snapshots.json", bundle.get("source_snapshots", []))
    _write_json(root / "source_fragments.json", bundle.get("source_fragments", []))
    _write_json(root / "source_parse_traces.json", bundle.get("source_parse_traces", []))
    _write_json(root / "source_fetch_metadata.json", bundle.get("source_fetch_metadata", []))
    _write_json(root / "source_fetch_attempts.json", bundle.get("source_fetch_attempts", []))
    _write_json(root / "source_target_links.json", bundle.get("source_target_links", []))
    _write_json(root / "source_inventory.json", bundle.get("source_inventory", {}))
    _write_json(
        root / "source_categorisation_rationales.json",
        bundle.get("source_categorisation_rationales", []),
    )
    _write_json(root / "run_artifacts.json", bundle.get("run_artifacts", []))
    _write_json(root / "source_family_candidates.json", bundle.get("source_family_candidates", []) or [])
    _write_json(
        root / "pipeline_review_decisions.json",
        bundle.get("pipeline_review_decisions", []),
    )
    quality = bundle.get("run_quality_summary")
    if isinstance(quality, dict):
        _write_json(root / "run_quality_summary.json", quality)
    _write_json(root / "proposition_inventory.json", bundle.get("proposition_inventory", {}))
    _write_json(root / "proposition_extraction_traces.json", bundle.get("proposition_extraction_traces", []))
    _write_json(root / "proposition_extraction_jobs.json", bundle.get("proposition_extraction_jobs", []))
    pexf = bundle.get("proposition_extraction_failures")
    if isinstance(pexf, list):
        _write_json(root / "proposition_extraction_failures.json", pexf)
    llm_tr = bundle.get("extraction_llm_call_traces")
    if isinstance(llm_tr, list):
        _write_json(root / "extraction_llm_call_traces.json", llm_tr)
    chunk_statuses = bundle.get("proposition_extraction_chunk_statuses")
    if isinstance(chunk_statuses, list) and chunk_statuses:
        _write_json(root / "proposition_extraction_chunk_statuses.json", chunk_statuses)
    inspection_summary = bundle.get("extraction_inspection_summary")
    if isinstance(inspection_summary, dict) and inspection_summary:
        _write_json(root / "extraction_inspection_summary.json", inspection_summary)
    pci = bundle.get("pipeline_case_inputs")
    if isinstance(pci, dict) and pci:
        _write_json(root / "pipeline_case_inputs.json", pci)
    pexf = bundle.get("proposition_extraction_failures")
    if isinstance(pexf, list):
        _write_json(root / "proposition_extraction_failures.json", pexf)
    llm_tr = bundle.get("extraction_llm_call_traces")
    if isinstance(llm_tr, list):
        _write_json(root / "extraction_llm_call_traces.json", llm_tr)
    pci = bundle.get("pipeline_case_inputs")
    if isinstance(pci, dict):
        _write_json(root / "pipeline_case_inputs.json", pci)
    pd_meta = bundle.get("proposition_dataset")
    if isinstance(pd_meta, dict) and pd_meta:
        _write_json(root / "proposition_dataset.json", pd_meta)
    dcr = bundle.get("dataset_comparison_run")
    if isinstance(dcr, dict) and dcr:
        _write_json(root / "dataset_comparison_run.json", dcr)
    _write_json(
        root / "proposition_completeness_assessments.json",
        bundle.get("proposition_completeness_assessments", []),
    )
    _write_json(root / "propositions.json", bundle["propositions"])
    prel = bundle.get("proposition_relationships")
    if isinstance(prel, dict) and prel:
        _write_json(root / "proposition-relationships.json", prel)
    lawstmts = bundle.get("effective_law_statements")
    if isinstance(lawstmts, dict) and lawstmts:
        _write_json(root / "effective_law_statements.json", lawstmts)
    bcands = bundle.get("proposition_matcher_law_candidates")
    if isinstance(bcands, dict) and bcands:
        _write_json(root / "proposition_matcher_law_candidates.json", bcands)
    lrg = bundle.get("legal_rule_groups")
    if isinstance(lrg, dict) and lrg:
        _write_json(root / "legal_rule_groups.json", lrg)
    lrr = bundle.get("legal_rule_relationships")
    if isinstance(lrr, dict) and lrr:
        _write_json(root / "legal_rule_relationships.json", lrr)
    sle = bundle.get("source_legal_effects")
    if isinstance(sle, dict) and sle:
        _write_json(root / "source_legal_effects.json", sle)
    dexp = bundle.get("decision_explanations")
    if isinstance(dexp, dict) and dexp:
        _write_json(root / "decision_explanations.json", dexp)
    _write_json(root / "divergence_assessments.json", bundle["divergence_assessments"])
    _write_json(root / "divergence_observations.json", bundle["divergence_observations"])
    _write_json(root / "divergence_findings.json", bundle["divergence_findings"])
    _write_json(root / "legal_scopes.json", bundle.get("legal_scopes", []))
    _write_json(root / "proposition_scope_links.json", bundle.get("proposition_scope_links", []))
    _write_json(root / "scope_inventory.json", bundle.get("scope_inventory", {}))
    _write_json(
        root / "scope_review_candidates.json",
        bundle.get("scope_review_candidates", []),
    )

    narrative = bundle["narrative"]
    (root / "narrative.md").write_text(
        "# "
        + narrative["title"]
        + "\n\n"
        + narrative["summary"]
        + "\n\n"
        + "\n".join(f"- {section}" for section in narrative["sections"]),
        encoding="utf-8",
    )
    _write_run_artifacts(
        bundle=bundle,
        root=root,
        final_export_timestamp=export_timestamp,
        final_export_duration_ms=int((perf_counter() - export_started_at) * 1000),
    )
