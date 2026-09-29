import json
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.operations import OperationsError, OperationalStore
from law_proposition_extractor_pipeline.runner import run_registry_sources
from law_proposition_extractor_pipeline.sources import SourceRegistryService


def test_source_detail_resolves_run_scoped_record_with_root_sources_mirror(
    tmp_path: Path,
) -> None:
    """Per-run source_records artifact may be empty while root sources.json mirrors that run."""
    run_id = "run-registry-20260430162937"
    source_id = "equine-law-eu-2016-429-art109"
    runs_dir = tmp_path / "runs" / run_id
    runs_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "artifacts": [
            {
                "artifact_type": "source_records",
                "storage_uri": f"runs/{run_id}/sources_pack.json",
            },
        ],
    }
    (runs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs_dir / "run.json").write_text(json.dumps({"id": run_id}), encoding="utf-8")
    (runs_dir / "sources_pack.json").write_text(json.dumps([]), encoding="utf-8")

    (tmp_path / "run.json").write_text(json.dumps({"id": run_id}), encoding="utf-8")
    root_sources = [
        {"id": source_id, "title": "Animal Health Law art109", "jurisdiction": "EU"},
    ]
    (tmp_path / "sources.json").write_text(json.dumps(root_sources), encoding="utf-8")

    store = OperationalStore(export_dir=tmp_path)
    listed = store.list_source_records(run_id=run_id)
    assert any(item["id"] == source_id for item in listed["source_records"])

    detail = store.get_source_detail(source_id=source_id, run_id=run_id)
    assert detail["run_id"] == run_id
    assert detail["source_id"] == source_id
    assert detail["source_record"]["id"] == source_id
    assert detail["partial"] is True


def test_source_detail_inventory_summary_fallback_is_partial(tmp_path: Path) -> None:
    """When source_records are missing but source_inventory has rows, expose summary-only records."""
    run_id = "run-inv-only"
    src = "src-from-inv"
    runs_dir = tmp_path / "runs" / run_id
    runs_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "artifacts": [
            {
                "artifact_type": "source_records",
                "storage_uri": f"runs/{run_id}/sources_pack.json",
            },
            {
                "artifact_type": "source_inventory",
                "storage_uri": f"runs/{run_id}/source_inventory.json",
            },
        ],
    }
    (runs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs_dir / "run.json").write_text(json.dumps({"id": run_id}), encoding="utf-8")
    (runs_dir / "sources_pack.json").write_text(json.dumps([]), encoding="utf-8")
    inv = {
        "rows": [
            {
                "source_record_id": src,
                "title": "Instrument",
                "jurisdiction": "EU",
                "instrument_id": "eur/2016/429",
                "instrument_type": "regulation",
                "status": "active",
                "content_hash": "abc",
            },
        ],
    }
    (runs_dir / "source_inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    (tmp_path / "run.json").write_text(json.dumps({"id": "other-export-root"}), encoding="utf-8")

    store = OperationalStore(export_dir=tmp_path)
    detail = store.get_source_detail(source_id=src, run_id=run_id)
    assert detail["source_record"]["id"] == src
    assert detail["partial"] is True
    assert "_summary_only" not in detail["source_record"]


def test_get_source_detail_unknown_source_raises(tmp_path: Path) -> None:
    run_id = "run-missing-src"
    runs_dir = tmp_path / "runs" / run_id
    runs_dir.mkdir(parents=True)
    manifest = {"run_id": run_id, "artifacts": []}
    (runs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs_dir / "run.json").write_text(json.dumps({"id": run_id}), encoding="utf-8")

    store = OperationalStore(export_dir=tmp_path)
    with pytest.raises(OperationsError):
        store.get_source_detail(source_id="nope", run_id=run_id)


def test_operational_store_reads_runs_sources_traces_and_reviews(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    source_id = str(bundle["source_records"][0]["id"])

    store = OperationalStore(export_dir=tmp_path)

    runs = store.list_runs()
    assert runs
    assert runs[0]["run_id"] == run_id

    inspected_run = store.inspect_run(run_id=run_id)
    assert inspected_run["run"]["id"] == run_id
    assert inspected_run["manifest"]["run_id"] == run_id

    sources_payload = store.list_source_records(run_id=run_id)
    assert len(sources_payload["source_records"]) == len(bundle["source_records"])
    assert any(item["id"] == source_id for item in sources_payload["source_records"])
    source_target_links_payload = store.list_source_target_links(run_id=run_id)
    assert source_target_links_payload["source_target_links"]
    assert any(
        item["source_record_id"] == source_id
        for item in source_target_links_payload["source_target_links"]
    )
    source_fetch_attempts_payload = store.list_source_fetch_attempts(run_id=run_id)
    assert source_fetch_attempts_payload["source_fetch_attempts"]
    assert any(
        item["source_record_id"] == source_id
        for item in source_fetch_attempts_payload["source_fetch_attempts"]
    )

    inspected_source = store.inspect_source_record(source_id=source_id, run_id=run_id)
    assert inspected_source["source_record"]["id"] == source_id

    snapshots = store.list_source_snapshots(source_id=source_id, run_id=run_id)
    assert snapshots["source_snapshots"]
    assert all(item["source_record_id"] == source_id for item in snapshots["source_snapshots"])

    all_snapshots = store.list_all_source_snapshots(run_id=run_id)
    assert all_snapshots["source_snapshots"]
    first_snapshot = all_snapshots["source_snapshots"][0]
    assert "authoritative_text" not in first_snapshot
    assert first_snapshot["has_authoritative_text"] is True
    snapshot_id = str(first_snapshot["id"])
    content = store.get_source_snapshot_content(snapshot_id=snapshot_id, run_id=run_id)
    assert content["available"] is True
    assert content["content"]
    assert content["snapshot_id"] == snapshot_id

    timeline = store.source_snapshot_timeline(source_id=source_id, run_id=run_id)
    assert timeline["timepoint_count"] == len(timeline["timepoints"])
    assert timeline["timepoint_count"] >= 1
    first_timepoint = timeline["timepoints"][0]
    assert first_timepoint["event_id"].startswith("snapshot-event::")
    assert first_timepoint["source_record_id"] == source_id
    assert "comparison" in first_timepoint

    fragments = store.list_source_fragments(source_id=source_id, run_id=run_id)
    assert fragments["source_fragments"]
    assert all(item["source_record_id"] == source_id for item in fragments["source_fragments"])
    filtered_fragments = store.list_source_fragments_filtered(
        run_id=run_id,
        source_record_id=source_id,
    )
    assert filtered_fragments["source_fragments"]
    source_snapshot_id = filtered_fragments["source_fragments"][0]["source_snapshot_id"]
    filtered_parse_traces = store.list_source_parse_traces(
        run_id=run_id,
        source_snapshot_id=source_snapshot_id,
    )
    assert filtered_parse_traces["source_parse_traces"]
    assert all(
        item["source_snapshot_id"] == source_snapshot_id
        for item in filtered_parse_traces["source_parse_traces"]
    )

    traces = store.list_stage_traces(run_id=run_id, compact=False)
    assert traces["trace_count"] >= 7
    assert traces["traces"][0]["trace"]["run_id"] == run_id

    decisions = store.list_review_decisions(run_id=run_id)
    assert decisions["review_decisions"]

    quality = store.read_run_quality_summary(run_id=run_id)
    assert quality["run_quality_summary"]["run_id"] == run_id

    law_statements = store.read_effective_law_statements(run_id=run_id)
    assert law_statements["run_id"] == run_id
    assert law_statements["statement_count"] >= 1
    assert isinstance(law_statements["effective_law_statements"]["statements"], list)

    beatrice_candidates = store.read_proposition_matcher_law_candidates(run_id=run_id)
    assert beatrice_candidates["run_id"] == run_id
    assert beatrice_candidates["candidate_count"] >= 0
    assert isinstance(beatrice_candidates["proposition_matcher_law_candidates"]["candidates"], list)

    propositions = store.list_propositions(run_id=run_id)
    assert propositions["propositions"]
    first_prop_id = str(propositions["propositions"][0]["id"])
    pex = store.list_proposition_extraction_traces(
        run_id=run_id,
        proposition_id=first_prop_id,
    )
    assert pex["proposition_extraction_traces"]
    assert pex["proposition_extraction_traces"][0]["proposition_id"] == first_prop_id
    pca = store.list_proposition_completeness_assessments(
        run_id=run_id,
        proposition_id=first_prop_id,
    )
    assert pca["proposition_completeness_assessments"]
    assert pca["proposition_completeness_assessments"][0]["proposition_id"] == first_prop_id
    pex_by_source = store.list_proposition_extraction_traces(
        run_id=run_id,
        source_record_id=source_id,
    )
    assert pex_by_source["proposition_extraction_traces"]
    assert all(
        item.get("source_record_id") == source_id
        for item in pex_by_source["proposition_extraction_traces"]
    )
    proposition_key = str(propositions["propositions"][0]["proposition_key"])
    proposition_history = store.proposition_history(proposition_key=proposition_key)
    assert proposition_history["proposition_key"] == proposition_key
    assert proposition_history["observed_version_count"] >= 1
    first_observation = proposition_history["observed_versions"][0]
    assert first_observation["proposition_version_id"]
    assert first_observation["source_record_id"] == source_id
    assert first_observation["previous_version_signal"] in {
        "text_changed",
        "metadata_changed",
        "both",
        "no_change",
    }
    assert proposition_history["versions_by_run"]
    assert proposition_history["versions_by_snapshot"]

    divergence_payload = store.list_divergence_assessments(run_id=run_id)
    assert divergence_payload["divergence_assessments"]
    first_assessment = divergence_payload["divergence_assessments"][0]
    finding_id = str(
        first_assessment.get("finding_id")
        or "finding-"
        + str(first_assessment.get("proposition_id", ""))
        + "-"
        + str(first_assessment.get("comparator_proposition_id", ""))
    )
    divergence_history = store.divergence_history(finding_id=finding_id)
    assert divergence_history["finding_id"] == finding_id
    assert divergence_history["observed_version_count"] >= 1
    observed_version = divergence_history["observed_versions"][0]
    assert observed_version["observation_id"]
    assert observed_version["version_identity"]
    assert isinstance(observed_version["source_record_ids"], list)
    assert isinstance(observed_version["source_snapshot_ids"], list)
    assert observed_version["previous_version_signal"] in {"initial", "changed", "no_change"}
    assert divergence_history["versions_by_run"]
    assert divergence_history["versions_by_snapshot"]


def test_operational_store_aggregates_source_history_across_runs_and_registry(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "source-registry.json"
    source_cache_dir = tmp_path / "source-cache"
    derived_cache_dir = tmp_path / "derived-cache"

    registry = SourceRegistryService(
        registry_path=registry_path,
        source_cache_dir=source_cache_dir,
    )
    registry_entry = registry.register_reference(
        reference={
            "authority": "case_file",
            "authority_source_id": "eu-source-agg-001",
            "id": "src-eu-agg-001",
            "title": "EU source aggregation",
            "jurisdiction": "EU",
            "citation": "EU-AGG-001",
            "kind": "regulation",
            "text": "Article 10. Operators must maintain a movement register before dispatch.",
            "authoritative_locator": "article:10",
            "version_id": "v1",
        },
        refresh=True,
    )
    source_id = str(registry_entry["current_state"]["source_record"]["id"])

    run_one = run_registry_sources(
        registry_ids=[registry_entry["registry_id"]],
        topic_name="Aggregated history run one",
        analysis_mode="single_jurisdiction",
        run_id="run-agg-001",
        source_registry_path=str(registry_path),
        source_cache_dir=str(source_cache_dir),
        derived_cache_dir=str(derived_cache_dir),
        use_llm=False,
    )
    export_bundle(bundle=run_one, output_dir=str(tmp_path))

    state_path = Path(registry_path)
    payload = state_path.read_text(encoding="utf-8")

    state = json.loads(payload)
    source_items = state.get("sources", [])
    for item in source_items:
        if item.get("registry_id") == registry_entry["registry_id"]:
            reference = item.get("reference", {})
            if isinstance(reference, dict):
                reference["text"] = (
                    "Article 10. Operators must keep a movement register before dispatch. "
                    "Authorities may request submission within 24 hours."
                )
                reference["version_id"] = "v2"
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    registry.refresh_reference(registry_id=registry_entry["registry_id"])

    run_two = run_registry_sources(
        registry_ids=[registry_entry["registry_id"]],
        topic_name="Aggregated history run two",
        analysis_mode="single_jurisdiction",
        run_id="run-agg-002",
        source_registry_path=str(registry_path),
        source_cache_dir=str(source_cache_dir),
        derived_cache_dir=str(derived_cache_dir),
        use_llm=False,
    )
    export_bundle(bundle=run_two, output_dir=str(tmp_path))

    store = OperationalStore(export_dir=tmp_path, source_registry_path=registry_path)
    history = store.source_snapshot_history(
        source_id=source_id,
        include_runs=True,
        include_registry=True,
    )

    assert history["scope"] == "aggregated_history"
    assert history["timepoint_count"] >= 2
    assert "run-agg-001" in history["run_ids_scanned"]
    assert "run-agg-002" in history["run_ids_scanned"]
    assert registry_entry["registry_id"] in history["registry_ids_matched"]
    assert history["timepoints"][0]["event_id"].startswith("snapshot-event::")
    assert any(
        any(origin.get("kind") == "run_snapshot" for origin in timepoint.get("origins", []))
        for timepoint in history["timepoints"]
    )
    assert any(
        any(origin.get("kind") == "registry_refresh" for origin in timepoint.get("origins", []))
        for timepoint in history["timepoints"]
    )

    proposition_key = str(run_one["propositions"][0]["proposition_key"])
    proposition_history = store.proposition_history(
        proposition_key=proposition_key,
        include_runs=True,
    )
    assert proposition_history["proposition_key"] == proposition_key
    assert proposition_history["observed_version_count"] >= 2
    assert "run-agg-001" in proposition_history["run_ids_scanned"]
    assert "run-agg-002" in proposition_history["run_ids_scanned"]
    assert len(proposition_history["versions_by_run"]) >= 2
    assert proposition_history["versions_by_snapshot"]
    latest = proposition_history["observed_versions"][-1]
    assert latest["proposition_version_id"]
    assert latest["source_record_id"] == source_id
    assert latest["source_snapshot_id"]
    assert latest["observed_in_run_id"]
    assert latest["legal_subject"]
    assert latest["action"]
    assert latest["proposition_text"]
    signal = latest["previous_version_signal"]
    assert signal in {"text_changed", "metadata_changed", "both", "no_change"}
