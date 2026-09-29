from pathlib import Path

import pytest

from law_proposition_extractor_exporters.static_bundle import export_static_bundle
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, lint_export_dir


def test_lint_export_dir_passes_for_demo_bundle(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_static_bundle(bundle=bundle, output_dir=str(tmp_path))

    report = lint_export_dir(export_dir=tmp_path)
    assert report["ok"] is True
    assert report["error_count"] == 0
    assert report["run_quality_summary"]["status"] in {"pass", "pass_with_warnings"}
    assert report["run_quality_summary"]["error_count"] == 0


def test_lint_bundle_flags_missing_lineage_and_invalid_category() -> None:
    bundle = build_demo_bundle(use_llm=False)
    first_proposition = bundle["propositions"][0]
    first_proposition["source_snapshot_id"] = ""
    first_proposition["source_record_id"] = "source-missing"
    first_proposition["categories"] = ["not_a_real_category"]
    bundle["run_artifacts"][0]["content_hash"] = ""

    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert report["error_count"] >= 4
    assert any("missing source_snapshot_id" in item for item in report["errors"])
    assert any("orphan proposition" in item for item in report["errors"])
    assert any("invalid proposition category" in item for item in report["errors"])
    assert any("run_artifact missing content_hash" in item for item in report["errors"])


def test_lint_bundle_flags_missing_source_categorisation_rationale() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["source_categorisation_rationales"] = []

    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("without rationale" in item for item in report["errors"])


def test_lint_bundle_flags_missing_source_target_links() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["source_target_links"] = []

    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("missing source_target_link" in item for item in report["errors"])


def test_lint_warns_when_distinct_sources_share_content_hash_and_snapshot_id() -> None:
    bundle = build_demo_bundle(use_llm=False)
    eu = next(
        s
        for s in bundle["source_records"]
        if isinstance(s, dict) and str(s.get("id", "")).strip() == "src-eu-001"
    )
    uk = next(
        s
        for s in bundle["source_records"]
        if isinstance(s, dict) and str(s.get("id", "")).strip() == "src-uk-001"
    )
    shared_hash = str(eu.get("content_hash") or "").strip()
    eu_snap = str(eu.get("current_snapshot_id") or "").strip()
    if not shared_hash or not eu_snap:
        pytest.skip("demo bundle missing content_hash or current_snapshot_id on EU source")
    uk["content_hash"] = shared_hash
    uk["current_snapshot_id"] = eu_snap

    report = lint_bundle(bundle)
    assert any("unexpected snapshot identity collapse" in w for w in report["warnings"])


def test_lint_bundle_flags_missing_fetch_attempts_and_hash() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["source_fetch_attempts"] = []
    report_missing_attempts = lint_bundle(bundle)
    assert report_missing_attempts["ok"] is False
    assert any("has no fetch attempt" in item for item in report_missing_attempts["errors"])

    bundle_with_attempts = build_demo_bundle(use_llm=False)
    first_attempt = bundle_with_attempts["source_fetch_attempts"][0]
    first_attempt["status"] = "success"
    first_attempt["content_hash"] = ""
    report_missing_hash = lint_bundle(bundle_with_attempts)
    assert report_missing_hash["ok"] is False
    assert any("no content_hash" in item for item in report_missing_hash["errors"])


def test_lint_bundle_flags_fragment_lineage_hash_and_parse_trace_mismatches() -> None:
    bundle = build_demo_bundle(use_llm=False)
    first_fragment = bundle["source_fragments"][0]
    first_fragment_source_record_id = str(first_fragment["source_record_id"])
    first_snapshot_id = str(first_fragment["source_snapshot_id"])
    first_fragment_id = str(first_fragment["id"])
    first_proposition = bundle["propositions"][0]

    first_fragment["source_record_id"] = ""
    first_fragment["source_snapshot_id"] = ""
    first_fragment["text_hash"] = ""
    first_fragment["fragment_hash"] = ""
    first_fragment["fragment_type"] = "unknown"
    first_fragment["locator"] = ""

    duplicate_fragment = {
        **first_fragment,
        "id": first_fragment_id,
        "source_record_id": first_fragment_source_record_id,
        "source_snapshot_id": first_snapshot_id,
        "fragment_hash": "dup-hash",
        "text_hash": "dup-hash",
    }
    bundle["source_fragments"].append(duplicate_fragment)

    first_proposition["source_fragment_id"] = "frag-missing"
    first_proposition["source_snapshot_id"] = "snap-missing"

    bundle["source_parse_traces"] = [
        {
            **bundle["source_parse_traces"][0],
            "source_snapshot_id": first_snapshot_id,
            "status": "failed",
        }
    ]

    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("source fragment has no source_record_id" in item for item in report["errors"])
    assert any("source fragment has no source_snapshot_id" in item for item in report["errors"])
    assert any("source fragment has no text hash" in item for item in report["errors"])
    assert any("missing source fragment" in item for item in report["errors"])
    assert any("missing source_snapshot_id" in item or "not found" in item for item in report["errors"])
    assert any("fragment_type unknown" in item for item in report["warnings"])
    assert any("locator missing" in item for item in report["warnings"])
    assert any("duplicate source fragment id exists" in item for item in report["warnings"])
    assert any("parse trace status failed but fragments exist" in item for item in report["warnings"])


def test_lint_bundle_warns_legacy_when_extraction_traces_not_enforced() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_extraction_traces"] = []
    bundle["has_proposition_extraction_traces"] = False
    report = lint_bundle(bundle)
    assert any("legacy bundle" in item for item in report["warnings"])


def test_lint_bundle_flags_missing_proposition_extraction_trace() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_extraction_traces"] = []
    bundle["has_proposition_extraction_traces"] = True
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("missing extraction trace" in item for item in report["errors"])


def test_lint_bundle_flags_extraction_trace_broken_refs() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_extraction_traces"][0]["source_fragment_id"] = "frag-missing"
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("source_fragment_id not found" in item for item in report["errors"])


def test_lint_bundle_flags_fallback_extraction_without_reason() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["proposition_extraction_traces"][0]["extraction_method"] = "fallback"
    bundle["proposition_extraction_traces"][0]["reason"] = ""
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("fallback without reason" in item for item in report["errors"])


def test_lint_bundle_flags_duplicate_extraction_trace_ids() -> None:
    bundle = build_demo_bundle(use_llm=False)
    traces = bundle["proposition_extraction_traces"]
    assert len(traces) >= 2
    traces[1]["id"] = traces[0]["id"]
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("duplicate extraction trace id" in item for item in report["errors"])


def test_lint_deduplicates_same_fragmentary_warning() -> None:
    bundle = build_demo_bundle(use_llm=False)
    pid = str(bundle["propositions"][0]["id"])
    bundle["proposition_completeness_assessments"] = [
        {
            "id": f"pca-{pid}-1",
            "proposition_id": pid,
            "status": "fragmentary",
            "reason": "test",
        },
        {
            "id": f"pca-{pid}-2",
            "proposition_id": pid,
            "status": "fragmentary",
            "reason": "test",
        },
    ]
    report = lint_bundle(bundle)
    matches = [w for w in report["warnings"] if f"fragmentary proposition has no pipeline_review_decision: {pid}" in w]
    assert len(matches) == 1


def test_lint_bundle_flags_extraction_trace_fragment_snapshot_mismatch() -> None:
    bundle = build_demo_bundle(use_llm=False)
    trace = bundle["proposition_extraction_traces"][0]
    frag_id = str(trace.get("source_fragment_id") or "").strip()
    if not frag_id:
        return
    fragment = next(
        (f for f in bundle["source_fragments"] if str(f.get("id")) == frag_id),
        None,
    )
    assert isinstance(fragment, dict)
    frag_snap = str(fragment.get("source_snapshot_id", "")).strip()
    alt_snap = next(
        (
            str(s.get("id"))
            for s in bundle["source_snapshots"]
            if str(s.get("id")) != frag_snap
        ),
        None,
    )
    if not alt_snap:
        pytest.skip("multiple snapshots required for fragment/snapshot mismatch scenario")
    trace["source_snapshot_id"] = alt_snap
    report = lint_bundle(bundle)
    assert report["ok"] is False
    assert any("mismatched fragment/snapshot" in item for item in report["errors"])


def test_lint_export_dir_loads_old_bundle_without_new_files(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text('{"id":"run-old-001"}', encoding="utf-8")
    (tmp_path / "sources.json").write_text("[]", encoding="utf-8")
    (tmp_path / "propositions.json").write_text("[]", encoding="utf-8")
    (tmp_path / "divergence_observations.json").write_text("[]", encoding="utf-8")
    (tmp_path / "run_artifacts.json").write_text("[]", encoding="utf-8")

    report = lint_export_dir(export_dir=tmp_path)
    assert report["run_id"] == "run-old-001"
    assert report["ok"] is False
    assert report["error_count"] >= 1
