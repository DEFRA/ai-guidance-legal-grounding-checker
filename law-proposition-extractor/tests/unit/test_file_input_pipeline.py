import json
import re
from pathlib import Path

from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.runner import (
    _opaque_proposition_extraction_trace_id,
    build_bundle_from_case,
    run_case_file,
)


def test_case_file_pipeline() -> None:
    case_path = Path("data/demo/example_case.json")
    bundle = run_case_file(str(case_path), use_llm=False)

    assert bundle["topic"]["name"] == "Movement record keeping"
    assert bundle.get("proposition_extraction_trace_count") == len(bundle["propositions"])
    assert bundle["workflow_mode"] == "divergence"
    assert bundle["has_divergence_outputs"] is True
    assert len(bundle["sources"]) == 2
    assert len(bundle["source_fetch_metadata"]) == 2
    assert len(bundle["source_target_links"]) == 2
    assert len(bundle["source_inventory"]["rows"]) == 2
    assert len(bundle["source_categorisation_rationales"]) == 2
    assert len(bundle["propositions"]) >= 2
    assert bundle["proposition_inventory"]["proposition_count"] == len(bundle["propositions"])
    assert len(bundle["divergence_assessments"]) == 1
    assert len(bundle["divergence_observations"]) == len(bundle["divergence_assessments"])
    assert len(bundle["divergence_findings"]) == len(bundle["divergence_observations"])
    assert bundle["divergence_assessments"][0]["divergence_type"] == "institutional"
    source_intake_trace = next(
        item for item in bundle["stage_traces"] if item["stage_name"] == "source intake"
    )
    fetch_cache_traces = source_intake_trace["outputs"]["fetch_cache_traces"]
    assert len(fetch_cache_traces) == 2
    assert source_intake_trace["outputs"]["source_fetch_attempt_ids"]
    assert source_intake_trace["outputs"]["source_parse_trace_ids"]
    intake_metrics = source_intake_trace["metrics"]
    assert intake_metrics["source_count"] == 2
    assert intake_metrics["snapshot_count"] == len(bundle["source_snapshots"])
    assert intake_metrics["parsed_snapshot_count"] == len(bundle["source_parse_traces"])
    assert intake_metrics["fragment_count"] == len(bundle["source_fragments"])
    assert intake_metrics["parser_success_count"] == len(bundle["source_parse_traces"])
    assert intake_metrics["parser_partial_success_count"] == 0
    assert intake_metrics["parser_failed_count"] == 0
    assert intake_metrics["parser_skipped_count"] == 0
    assert intake_metrics["unique_fragment_hash_count"] >= 1
    assert "cache_hit_count" in intake_metrics
    assert "live_fetch_count" in intake_metrics
    assert "success_count" in intake_metrics
    assert "retryable_error_count" in intake_metrics
    assert "fatal_error_count" in intake_metrics
    assert "skipped_count" in intake_metrics
    assert "unique_content_hash_count" in intake_metrics
    assert all(
        item["decision"] in {"fetched_then_cached", "cache_hit"} for item in fetch_cache_traces
    )
    extraction_trace = next(
        item for item in bundle["stage_traces"] if item["stage_name"] == "proposition extraction"
    )
    assert extraction_trace["metrics"]["traced_proposition_count"] == len(bundle["propositions"])
    assert extraction_trace["metrics"]["heuristic_extraction_count"] >= 1
    assert extraction_trace["outputs"]["proposition_extraction_trace_ids"]
    classification_trace = next(
        item for item in bundle["stage_traces"] if item["stage_name"] == "divergence classification"
    )
    narrative_trace = next(
        item for item in bundle["stage_traces"] if item["stage_name"] == "narrative generation"
    )
    assert extraction_trace["inputs"]["derived_artifact_cache"]["cache_status"] in {
        "cache_hit",
        "cache_miss_persisted",
    }
    assert classification_trace["inputs"]["derived_artifact_cache"]["cache_status"] in {
        "cache_hit",
        "cache_miss_persisted",
    }
    assert narrative_trace["inputs"]["derived_artifact_cache"]["cache_status"] in {
        "cache_hit",
        "cache_miss_persisted",
    }
    observation = bundle["divergence_observations"][0]
    assert observation["primary_source_fragment_id"]
    assert observation["comparator_source_fragment_id"]
    assert isinstance(observation["supporting_source_fragment_ids"], list)
    assert observation["context_note"]
    assert observation["why_these_fragments"]
    assert "evidence_context" in classification_trace["outputs"]
    assert (
        classification_trace["outputs"]["evidence_context"][0]["observation_id"]
        == observation["id"]
    )
    assert all(item["review_status"] == "proposed" for item in bundle["propositions"])
    assert all(item.get("proposition_key") for item in bundle["propositions"])
    for item in bundle["propositions"]:
        assert re.fullmatch(r"prop:[a-f0-9]{16}", str(item["id"]))
        key_parts = str(item["proposition_key"]).split(":")
        assert len(key_parts) == 3 and key_parts[2].startswith("p"), item["proposition_key"]
        assert item.get("label") and "\u2014" in item["label"]
        assert item.get("short_name")
        assert item.get("slug") and item["slug"] != item["id"]
    assert all(item.get("proposition_version_id") for item in bundle["propositions"])
    assert all(
        item.get("observed_in_run_id") == bundle["run"]["id"] for item in bundle["propositions"]
    )
    assert all(item.get("source_snapshot_id") for item in bundle["propositions"])
    assert bundle["proposition_inventory"].get("lineage_index")
    assert all(item.get("fetch_status") for item in bundle["source_fetch_metadata"])
    assert all(item.get("text_hash") for item in bundle["source_fragments"])
    assert all(item.get("source_snapshot_id") for item in bundle["source_fragments"])
    assert all(item.get("source_record_id") for item in bundle["source_fragments"])
    assert all(item.get("source_snapshot_id") for item in bundle["source_parse_traces"])
    assert all(item.get("output_fragment_ids") for item in bundle["source_parse_traces"])
    assert len(bundle["proposition_extraction_traces"]) == len(bundle["propositions"])
    for prop, pex in zip(bundle["propositions"], bundle["proposition_extraction_traces"], strict=True):
        assert pex["proposition_id"] == prop["id"]
        assert pex["proposition_key"] == prop["proposition_key"]
        assert pex["extraction_method"] == "heuristic"
        assert re.fullmatch(r"extract-trace:[a-f0-9]{16}", str(pex["id"]))
        assert pex["id"] == _opaque_proposition_extraction_trace_id(prop["id"])
    assert all(item.get("content_hash") for item in bundle["source_inventory"]["rows"])
    assert all(item.get("source_role") for item in bundle["source_inventory"]["rows"])
    assert all(
        item.get("relationship_to_analysis") for item in bundle["source_inventory"]["rows"]
    )
    link_by_source = {
        item["source_record_id"]: item for item in bundle["source_target_links"] if item.get("source_record_id")
    }
    relation_by_link = {
        "is_target": "analysis_target",
        "amends": "modifies_target",
        "corrects": "modifies_target",
        "implements": "implements_target",
        "supplements": "implements_target",
        "explains": "explains_target",
        "evidences": "evidences_target",
        "contains_annex_to": "contextual_source",
        "references": "contextual_source",
        "contextual": "contextual_source",
        "unknown": "unknown",
    }
    for row in bundle["source_inventory"]["rows"]:
        source_id = row["source_record_id"]
        assert source_id in link_by_source
        link_type = link_by_source[source_id]["link_type"]
        assert row["relationship_to_analysis"] == relation_by_link[link_type]
    assert all(item.get("method") for item in bundle["source_categorisation_rationales"])
    assert all(item.get("reason") for item in bundle["source_categorisation_rationales"])


def test_case_file_export_includes_run_quality_summary(tmp_path: Path) -> None:
    case_path = Path("data/demo/example_case.json")
    bundle = run_case_file(str(case_path), use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    summary_path = tmp_path / "run_quality_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == bundle["run"]["id"]
    assert summary["status"] in {"pass", "pass_with_warnings"}
    assert summary["source_count"] == len(bundle["sources"])


def test_realistic_case_file_pipeline() -> None:
    case_path = Path("data/demo/realistic_case.json")
    bundle = run_case_file(str(case_path), use_llm=False)

    divergence_types = {item["divergence_type"] for item in bundle["divergence_assessments"]}

    assert bundle["topic"]["name"] == "Movement records and submission duties"
    assert len(bundle["sources"]) == 2
    assert len(bundle["propositions"]) >= 4
    assert bundle["proposition_inventory"]["proposition_count"] == len(bundle["propositions"])
    assert len(bundle["divergence_assessments"]) >= 2
    assert len(bundle["divergence_observations"]) == len(bundle["divergence_assessments"])
    assert len(bundle["divergence_findings"]) == len(bundle["divergence_observations"])
    assert all(item["primary_source_fragment_id"] for item in bundle["divergence_observations"])
    assert all(item["comparator_source_fragment_id"] for item in bundle["divergence_observations"])
    assert "institutional" in divergence_types
    assert any(item != "institutional" for item in divergence_types)


def test_single_jurisdiction_case_pipeline() -> None:
    case_path = Path("data/demo/single_jurisdiction_case.json")
    bundle = run_case_file(str(case_path), use_llm=False)

    assert bundle["workflow_mode"] == "single_jurisdiction"
    assert bundle["has_divergence_outputs"] is False
    assert bundle["run"]["workflow_mode"] == "single_jurisdiction"
    assert len(bundle["sources"]) == 1
    assert len(bundle["propositions"]) >= 1
    assert bundle["proposition_inventory"]["proposition_count"] == len(bundle["propositions"])
    assert len(bundle["divergence_assessments"]) == 0
    assert len(bundle["divergence_observations"]) == 0
    pairing_trace = next(
        item for item in bundle["stage_traces"] if item["stage_name"] == "proposition pairing"
    )
    assert pairing_trace["outputs"]["pair_count"] == 0


def test_derived_artifact_cache_records_miss_then_hit(tmp_path: Path) -> None:
    case_data = json.loads(Path("data/demo/example_case.json").read_text(encoding="utf-8"))
    case_data["source_cache_dir"] = str(tmp_path / "source-cache")
    case_data["derived_cache_dir"] = str(tmp_path / "derived-cache")

    first_bundle = build_bundle_from_case(case_data=case_data, use_llm=False)
    second_bundle = build_bundle_from_case(case_data=case_data, use_llm=False)

    tracked_stages = {
        "proposition extraction",
        "divergence classification",
        "narrative generation",
    }
    first_stage_traces = {
        item["stage_name"]: item
        for item in first_bundle["stage_traces"]
        if item["stage_name"] in tracked_stages
    }
    second_stage_traces = {
        item["stage_name"]: item
        for item in second_bundle["stage_traces"]
        if item["stage_name"] in tracked_stages
    }

    assert set(first_stage_traces) == tracked_stages
    assert set(second_stage_traces) == tracked_stages

    for stage_name in tracked_stages:
        first_cache = first_stage_traces[stage_name]["inputs"]["derived_artifact_cache"]
        second_cache = second_stage_traces[stage_name]["inputs"]["derived_artifact_cache"]
        assert first_cache["cache_status"] == "cache_miss_persisted"
        assert second_cache["cache_status"] == "cache_hit"
        assert (
            first_cache["derived_artifact_cache_key"] == second_cache["derived_artifact_cache_key"]
        )
        assert isinstance(first_cache["cache_storage_uri"], str)
        assert isinstance(second_cache["cache_storage_uri"], str)


def test_cache_dir_precedence_and_trace_visibility(tmp_path: Path, monkeypatch) -> None:
    case_data = json.loads(Path("data/demo/example_case.json").read_text(encoding="utf-8"))
    case_data["source_cache_dir"] = str(tmp_path / "case-source-cache")
    case_data["derived_cache_dir"] = str(tmp_path / "case-derived-cache")

    monkeypatch.setenv("JUDIT_SOURCE_CACHE_DIR", str(tmp_path / "env-source-cache"))
    monkeypatch.setenv("JUDIT_DERIVED_CACHE_DIR", str(tmp_path / "env-derived-cache"))

    bundle_cli = build_bundle_from_case(
        case_data=case_data,
        use_llm=False,
        source_cache_dir=str(tmp_path / "cli-source-cache"),
        derived_cache_dir=str(tmp_path / "cli-derived-cache"),
    )
    intake_trace_cli = next(
        item for item in bundle_cli["stage_traces"] if item["stage_name"] == "source intake"
    )
    assert intake_trace_cli["inputs"]["cache_paths"]["source_cache_dir"] == str(
        tmp_path / "cli-source-cache"
    )
    assert intake_trace_cli["inputs"]["cache_paths"]["derived_cache_dir"] == str(
        tmp_path / "cli-derived-cache"
    )
    assert intake_trace_cli["inputs"]["cache_path_resolution"]["source_cache_dir"] == "cli_flag"
    assert intake_trace_cli["inputs"]["cache_path_resolution"]["derived_cache_dir"] == "cli_flag"

    bundle_case = build_bundle_from_case(case_data=case_data, use_llm=False)
    intake_trace_case = next(
        item for item in bundle_case["stage_traces"] if item["stage_name"] == "source intake"
    )
    assert intake_trace_case["inputs"]["cache_paths"]["source_cache_dir"] == str(
        tmp_path / "case-source-cache"
    )
    assert intake_trace_case["inputs"]["cache_paths"]["derived_cache_dir"] == str(
        tmp_path / "case-derived-cache"
    )
    assert intake_trace_case["inputs"]["cache_path_resolution"]["source_cache_dir"] == "case_file"
    assert intake_trace_case["inputs"]["cache_path_resolution"]["derived_cache_dir"] == "case_file"

    case_without_cache = dict(case_data)
    case_without_cache.pop("source_cache_dir", None)
    case_without_cache.pop("derived_cache_dir", None)
    bundle_env = build_bundle_from_case(case_data=case_without_cache, use_llm=False)
    intake_trace_env = next(
        item for item in bundle_env["stage_traces"] if item["stage_name"] == "source intake"
    )
    assert intake_trace_env["inputs"]["cache_paths"]["source_cache_dir"] == str(
        tmp_path / "env-source-cache"
    )
    assert intake_trace_env["inputs"]["cache_paths"]["derived_cache_dir"] == str(
        tmp_path / "env-derived-cache"
    )
    assert intake_trace_env["inputs"]["cache_path_resolution"]["source_cache_dir"] == "env_var"
    assert intake_trace_env["inputs"]["cache_path_resolution"]["derived_cache_dir"] == "env_var"
