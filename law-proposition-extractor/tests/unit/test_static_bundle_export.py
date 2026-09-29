import json
from pathlib import Path

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle


def test_export_static_bundle_keeps_flat_files_and_writes_run_artifacts(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    # Existing flat bundle files remain available for direct consumption.
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "topic.json").exists()
    assert (tmp_path / "divergence_assessments.json").exists()
    assert (tmp_path / "divergence_observations.json").exists()
    assert (tmp_path / "divergence_findings.json").exists()
    assert (tmp_path / "source_fetch_metadata.json").exists()
    assert (tmp_path / "source_fetch_attempts.json").exists()
    assert (tmp_path / "source_fragments.json").exists()
    assert (tmp_path / "source_parse_traces.json").exists()
    assert (tmp_path / "proposition_extraction_traces.json").exists()
    assert (tmp_path / "proposition_extraction_jobs.json").exists()
    assert (tmp_path / "proposition_completeness_assessments.json").exists()
    assert (tmp_path / "source_target_links.json").exists()
    assert (tmp_path / "source_inventory.json").exists()
    assert (tmp_path / "source_categorisation_rationales.json").exists()
    assert (tmp_path / "run_artifacts.json").exists()
    assert (tmp_path / "pipeline_review_decisions.json").exists()
    assert (tmp_path / "run_quality_summary.json").exists()
    assert (tmp_path / "proposition_inventory.json").exists()
    assert (tmp_path / "legal_scopes.json").exists()
    assert (tmp_path / "proposition_scope_links.json").exists()
    assert (tmp_path / "scope_inventory.json").exists()
    assert (tmp_path / "scope_review_candidates.json").exists()
    assert (tmp_path / "narrative.md").exists()
    assert (tmp_path / "MODEL.md").exists()
    assert (tmp_path / "proposition-relationships.json").exists()
    assert (tmp_path / "effective_law_statements.json").exists()
    assert (tmp_path / "proposition_matcher_law_candidates.json").exists()
    assert (tmp_path / "legal_rule_groups.json").exists()
    assert (tmp_path / "legal_rule_relationships.json").exists()

    run_id = bundle["run"]["id"]
    run_dir = tmp_path / "runs" / run_id
    artifacts_dir = run_dir / "artifacts"
    traces_dir = run_dir / "traces"

    assert run_dir.exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "run-artifacts.json").exists()
    assert (run_dir / "trace-manifest.json").exists()
    assert artifacts_dir.exists()
    assert traces_dir.exists()

    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    root_manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert root_manifest["workflow_mode"] == bundle["workflow_mode"]
    assert root_manifest["has_divergence_outputs"] is bundle["has_divergence_outputs"]
    assert root_manifest["has_source_fetch_attempts"] is True
    assert root_manifest["has_source_parse_traces"] is True
    assert root_manifest["source_parse_trace_count"] >= 1
    assert root_manifest["source_fragment_count"] >= 1
    assert root_manifest["has_source_target_links"] is True
    assert root_manifest["has_source_categorisation_rationales"] is True
    assert root_manifest["has_proposition_extraction_traces"] is True
    assert root_manifest["proposition_extraction_trace_count"] >= 1
    assert root_manifest["has_proposition_extraction_jobs"] is bool(
        bundle.get("proposition_extraction_jobs", [])
    )
    assert root_manifest["proposition_extraction_job_count"] == len(
        bundle.get("proposition_extraction_jobs", [])
    )
    assert root_manifest.get("has_proposition_completeness_assessments") is True
    assert root_manifest.get("proposition_completeness_assessment_count", 0) >= 1
    assert isinstance(root_manifest.get("proposition_completeness_status_counts"), dict)
    assert root_manifest["has_run_quality_summary"] is True
    assert root_manifest.get("has_pipeline_review_decisions") is False
    assert root_manifest.get("pipeline_review_decision_count") == 0
    assert root_manifest.get("legal_scope_count", 0) >= 10
    assert root_manifest.get("has_legal_scopes") is True
    assert run_manifest["run_id"] == run_id
    assert run_manifest["workflow_mode"] == bundle["workflow_mode"]
    assert run_manifest["proposition_count"] == len(bundle["propositions"])
    assert run_manifest["divergence_assessment_count"] == len(bundle["divergence_assessments"])
    assert run_manifest["artifact_count"] >= 2
    assert run_manifest["stage_trace_count"] == 7
    assert run_manifest["source_fetch_attempt_count"] >= 1
    assert run_manifest["source_parse_trace_count"] >= 1
    assert run_manifest["source_fragment_count"] >= 1
    assert run_manifest["source_target_link_count"] >= 1
    assert run_manifest["source_categorisation_rationale_count"] >= 1
    assert run_manifest["proposition_extraction_trace_count"] >= 1
    assert run_manifest["proposition_extraction_job_count"] == len(
        bundle.get("proposition_extraction_jobs", [])
    )
    assert run_manifest.get("has_proposition_completeness_assessments") is True
    assert run_manifest.get("proposition_completeness_assessment_count", 0) >= 1
    assert isinstance(run_manifest.get("proposition_completeness_status_counts"), dict)
    assert run_manifest.get("has_run_quality_summary") is True
    assert run_manifest["trace_manifest_uri"] == f"runs/{run_id}/trace-manifest.json"
    assert any(
        item["artifact_type"] == "divergence_assessments" for item in run_manifest["artifacts"]
    )
    assert any(item["artifact_type"] == "narrative_export" for item in run_manifest["artifacts"])
    assert any(item["artifact_type"] == "source_inventory" for item in run_manifest["artifacts"])
    assert any(
        item["artifact_type"] == "source_fetch_metadata" for item in run_manifest["artifacts"]
    )
    assert any(item["artifact_type"] == "source_fetch_attempts" for item in run_manifest["artifacts"])
    assert any(item["artifact_type"] == "source_fragments" for item in run_manifest["artifacts"])
    assert any(item["artifact_type"] == "source_parse_traces" for item in run_manifest["artifacts"])
    assert any(
        item["artifact_type"] == "proposition_extraction_traces"
        for item in run_manifest["artifacts"]
    )
    has_jobs_artifact = any(
        item.get("artifact_type") == "proposition_extraction_jobs"
        for item in run_manifest["artifacts"]
    )
    assert has_jobs_artifact is any(
        item.get("artifact_type") == "proposition_extraction_jobs"
        for item in bundle.get("run_artifacts", [])
    )
    assert any(
        item["artifact_type"] == "proposition_completeness_assessments"
        for item in run_manifest["artifacts"]
    )
    assert any(item["artifact_type"] == "source_target_links" for item in run_manifest["artifacts"])
    assert any(
        item["artifact_type"] == "source_categorisation_rationales"
        for item in run_manifest["artifacts"]
    )
    assert any(
        item["artifact_type"] == "run_quality_summary" for item in run_manifest["artifacts"]
    )

    trace_manifest = json.loads((run_dir / "trace-manifest.json").read_text(encoding="utf-8"))
    assert trace_manifest["run_id"] == run_id
    assert trace_manifest["stage_count"] == 7
    assert [item["stage_name"] for item in trace_manifest["stages"]] == [
        "source intake",
        "proposition extraction",
        "proposition inventory",
        "proposition pairing",
        "divergence classification",
        "narrative generation",
        "final export",
    ]

    first_trace_uri = trace_manifest["stages"][0]["storage_uri"]
    first_trace = json.loads((tmp_path / first_trace_uri).read_text(encoding="utf-8"))
    assert first_trace["stage_name"] == "source intake"
    assert first_trace["run_id"] == run_id
    assert isinstance(first_trace["timestamp"], str)
    assert isinstance(first_trace["started_at"], str)
    assert isinstance(first_trace["finished_at"], str)
    assert first_trace["status"] in {"ok", "failed"}
    assert isinstance(first_trace["inputs"], dict)
    assert isinstance(first_trace["outputs"], dict)
    assert isinstance(first_trace["strategy_used"], str)
    assert "model_alias_used" in first_trace
    assert isinstance(first_trace["duration_ms"], int)
    assert isinstance(first_trace["input_artifact_ids"], list)
    assert isinstance(first_trace["output_artifact_ids"], list)
    assert isinstance(first_trace["metrics"], dict)
    assert isinstance(first_trace["warnings"], list)
    assert isinstance(first_trace["errors"], list)

    for item in bundle["run_artifacts"]:
        storage_uri = item.get("storage_uri")
        assert isinstance(storage_uri, str)
        assert storage_uri.startswith(f"runs/{run_id}/artifacts/")
        assert (tmp_path / storage_uri).exists()

    eval_dir = run_dir / "evaluation"
    assert (eval_dir / "evaluation_report.json").exists()
    assert (eval_dir / "evaluation_summary.md").exists()
    eval_report = json.loads((eval_dir / "evaluation_report.json").read_text(encoding="utf-8"))
    assert eval_report["schema_version"] == "lpe-eval-v0.1"
    assert eval_report["run_id"] == run_id
