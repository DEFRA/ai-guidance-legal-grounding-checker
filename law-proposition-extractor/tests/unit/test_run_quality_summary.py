from pathlib import Path
import json

import pytest

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, lint_export_dir
from law_proposition_extractor_pipeline.operations import OperationsError, OperationalStore
from law_proposition_extractor_pipeline.run_quality import build_run_quality_summary


def test_build_run_quality_summary_pass_matches_lint_ok() -> None:
    bundle = build_demo_bundle(use_llm=False)
    lint_report = lint_bundle(bundle)
    summary = build_run_quality_summary(bundle, lint_report=lint_report)
    assert lint_report["ok"] is True
    assert summary["error_count"] == 0
    if lint_report["warning_count"] == 0:
        assert summary["status"] == "pass"
    else:
        assert summary["status"] == "pass_with_warnings"
    assert summary["source_count"] == len(bundle["source_records"])
    assert summary["gate_results"]
    assert all("gate_id" in g for g in summary["gate_results"])


def test_build_run_quality_summary_fail_when_lint_errors() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["propositions"][0]["source_snapshot_id"] = ""
    lint_report = lint_bundle(bundle)
    summary = build_run_quality_summary(bundle, lint_report=lint_report)
    assert lint_report["ok"] is False
    assert summary["status"] == "fail"
    assert summary["error_count"] > 0
    failed = [g for g in summary["gate_results"] if g["status"] == "fail"]
    assert failed


def test_build_run_quality_summary_pass_with_warnings() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["source_snapshots"][0]["parser_name"] = ""
    lint_report = lint_bundle(bundle)
    summary = build_run_quality_summary(bundle, lint_report=lint_report)
    assert lint_report["ok"] is True
    assert lint_report["warning_count"] > 0
    assert summary["status"] == "pass_with_warnings"


def test_export_bundle_writes_run_quality_summary_json(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    path = tmp_path / "run_quality_summary.json"
    assert path.exists()
    data = path.read_text(encoding="utf-8")
    assert bundle["run"]["id"] in data
    assert "gate_results" in data


def test_lint_export_dir_includes_computed_summary_without_export_file(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    # Only flat layout; no run_quality_summary.json (simulates pre-export lint).
    from law_proposition_extractor_exporters.static_bundle import export_static_bundle

    export_static_bundle(bundle=bundle, output_dir=str(tmp_path))
    assert not (tmp_path / "run_quality_summary.json").exists()
    report = lint_export_dir(export_dir=tmp_path)
    assert "run_quality_summary" in report
    assert report["run_quality_summary"]["run_id"] == bundle["run"]["id"]


def test_operational_store_read_run_quality_after_export_bundle(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    store = OperationalStore(export_dir=tmp_path)
    payload = store.read_run_quality_summary(run_id=str(bundle["run"]["id"]))
    assert payload["run_quality_summary"]["status"] in {
        "pass",
        "pass_with_warnings",
        "fail",
    }


def test_operational_store_run_quality_merges_repair_metrics_from_bundle(tmp_path: Path) -> None:
    """Stale root ``run_quality_summary.json`` must not hide repairable extraction from artifacts."""
    bundle = build_demo_bundle(use_llm=False)
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["insufficient credits for model call"]
        tr["confidence"] = "medium"
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": True}

    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    stale_path = tmp_path / "run_quality_summary.json"
    stale = json.loads(stale_path.read_text(encoding="utf-8"))
    stale["metrics"] = {"lint_ok": True}
    stale_path.write_text(json.dumps(stale), encoding="utf-8")

    store = OperationalStore(export_dir=tmp_path)
    payload = store.read_run_quality_summary(run_id=run_id)
    repair = payload["run_quality_summary"]["metrics"]["repairable_extraction"]
    assert repair["has_repairable_failures"] is True
    assert int(repair.get("repairable_chunk_count") or 0) >= 1
    assert repair.get("estimated_retry_tokens") is None
    assert repair.get("estimated_retry_token_count") is None
