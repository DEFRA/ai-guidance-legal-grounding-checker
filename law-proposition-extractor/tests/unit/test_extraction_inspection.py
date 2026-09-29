"""Regression tests for extraction failure / job inspection from exported bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.extraction_inspection import summarize_extraction_inspection, summarize_extraction_jobs
from law_proposition_extractor_pipeline.export import export_bundle, refresh_extraction_observability_in_bundle
from law_proposition_extractor_pipeline.linting import load_exported_bundle


def _three_job_bundle() -> dict:
    return {
        "run": {"id": "run-inspect", "workflow_mode": "single_jurisdiction"},
        "topic": {"name": "T", "description": "", "subject_tags": []},
        "clusters": [{"id": "c1", "name": "C", "description": ""}],
        "source_records": [{"id": "src-a", "title": "Source A"}],
        "propositions": [{"id": "prop-1", "source_record_id": "src-a"}],
        "proposition_extraction_traces": [{"id": "tr-1", "proposition_id": "prop-1"}],
        "proposition_extraction_jobs": [
            {
                "id": "job-ok",
                "selected_for_extraction": True,
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:1",
                "llm_invoked": True,
                "proposition_count": 1,
                "cache_status": "chunk_cache_miss",
                "errors": [],
            },
            {
                "id": "job-json",
                "selected_for_extraction": True,
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:2",
                "llm_invoked": True,
                "proposition_count": 0,
                "cache_status": "chunk_cache_miss",
                "errors": ["chunk 1/1: model call or JSON parse failed: Expecting value"],
                "repairable": True,
                "repair_reason": "json_parse_or_llm_failure",
            },
            {
                "id": "job-schema",
                "selected_for_extraction": True,
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:3",
                "llm_invoked": True,
                "proposition_count": 0,
                "cache_status": "chunk_cache_miss",
                "errors": ["chunk 1/1: schema validation failed: missing rule field"],
            },
        ],
        "extraction_llm_call_traces": [
            {
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:1",
                "llm_call_attempted": True,
                "llm_invoked": True,
                "llm_call_succeeded": True,
                "extraction_mode": "local",
                "model_alias": "local_extract",
            },
            {
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:2",
                "llm_call_attempted": True,
                "llm_invoked": True,
                "llm_call_succeeded": False,
                "model_error": "model call or JSON parse failed: Expecting value",
                "extraction_mode": "local",
                "model_alias": "local_extract",
                "parse_error_message": "Expecting value",
            },
            {
                "source_record_id": "src-a",
                "source_title": "Source A",
                "fragment_locator": "reg:3",
                "llm_call_attempted": True,
                "llm_invoked": True,
                "llm_call_succeeded": False,
                "model_error": "schema validation failed: missing rule field",
                "extraction_mode": "local",
                "model_alias": "local_extract",
            },
        ],
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {"extraction_mode": "local", "extraction_mode_effective": "local"},
            }
        ],
        "narrative": {"title": "N", "summary": "S", "sections": []},
    }


def test_inspect_extraction_failures_reports_failed_jobs_without_propositions() -> None:
    bundle = _three_job_bundle()
    refresh_extraction_observability_in_bundle(bundle)
    summary = summarize_extraction_inspection(bundle)

    assert summary["proposition_count"] == 1
    assert summary["extraction_jobs_total"] == 3
    assert summary["extraction_jobs_selected"] == 3
    assert summary["extraction_jobs_failed"] == 2
    assert summary["live_llm_calls_attempted"] == 3
    assert summary["live_llm_calls_successful"] == 1
    assert summary["live_llm_calls_failed"] == 2
    assert summary["attempted_llm_calls"] == summary["live_llm_calls_successful"] + summary["live_llm_calls_failed"]
    assert summary["failure_reasons_by_type"]
    assert summary["has_repairable_extraction_failures"] is True
    assert "json_parse_or_llm_failure" in summary["failure_reasons_by_type"]
    assert "schema_validation_error" in summary["failure_reasons_by_type"]


def test_inspect_extraction_jobs_lists_failure_examples() -> None:
    bundle = _three_job_bundle()
    jobs_summary = summarize_extraction_jobs(bundle)
    assert jobs_summary["extraction_jobs_successful"] == 1
    assert jobs_summary["extraction_jobs_failed"] == 2
    assert len(jobs_summary["failure_examples"]) == 2


def test_export_writes_inspection_artifacts(tmp_path: Path) -> None:
    bundle = _three_job_bundle()
    bundle.update(
        {
            "source_snapshots": [],
            "source_fragments": [],
            "source_parse_traces": [],
            "source_fetch_metadata": [],
            "source_fetch_attempts": [],
            "source_target_links": [],
            "source_inventory": {},
            "source_categorisation_rationales": [],
            "proposition_inventory": {},
            "run_artifacts": [],
            "legal_scopes": [],
            "proposition_scope_links": [],
            "scope_inventory": {},
            "scope_review_candidates": [],
        }
    )
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    loaded = load_exported_bundle(tmp_path)
    assert (tmp_path / "extraction_inspection_summary.json").is_file()
    assert (tmp_path / "proposition_extraction_chunk_statuses.json").is_file()
    assert loaded.get("extraction_inspection_summary")
    assert loaded.get("proposition_extraction_chunk_statuses")


def test_export_refreshes_stale_llm_metrics(tmp_path: Path) -> None:
    bundle = _three_job_bundle()
    bundle["run_quality_summary"] = {
        "run_id": "run-inspect",
        "status": "fail",
        "metrics": {
            "attempted_llm_calls": 99,
            "successful_llm_calls": 20,
            "failed_llm_calls": 99,
        },
    }
    bundle.update(
        {
            "source_snapshots": [],
            "source_fragments": [],
            "source_parse_traces": [],
            "source_fetch_metadata": [],
            "source_fetch_attempts": [],
            "source_target_links": [],
            "source_inventory": {},
            "source_categorisation_rationales": [],
            "proposition_inventory": {},
            "run_artifacts": [{"artifact_type": "run_quality_summary", "id": "artifact-run-inspect-run-quality-summary"}],
            "legal_scopes": [],
            "proposition_scope_links": [],
            "scope_inventory": {},
            "scope_review_candidates": [],
        }
    )
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["attempted_llm_calls"] == 3
    assert manifest["successful_llm_calls"] == 1
    assert manifest["failed_llm_calls"] == 2
    assert manifest["cached_llm_results_successful"] == 0
