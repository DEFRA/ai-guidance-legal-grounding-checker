from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_proposition_extractor_domain import PipelineReviewDecision
from law_proposition_extractor_exporters.static_bundle import export_static_bundle
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, load_exported_bundle
from law_proposition_extractor_pipeline.operations import OperationalStore
from law_proposition_extractor_pipeline.pipeline_reviews import (
    append_pipeline_review_decision,
    categorisation_artifact_id,
    resolve_current_pipeline_review_decision,
)


def test_resolve_current_respects_supersedes() -> None:
    decisions: list[dict] = [
        {
            "id": "a",
            "run_id": "r1",
            "artifact_type": "proposition",
            "artifact_id": "p1",
            "decision": "needs_review",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "",
        },
        {
            "id": "b",
            "run_id": "r1",
            "artifact_type": "proposition",
            "artifact_id": "p1",
            "decision": "approved",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "reason": "",
            "supersedes_decision_id": "a",
        },
    ]
    cur = resolve_current_pipeline_review_decision(
        decisions,
        artifact_type="proposition",
        artifact_id="p1",
    )
    assert cur is not None
    assert cur["id"] == "b"
    assert cur["decision"] == "approved"


def test_append_pipeline_review_decision_is_append_only(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    append_pipeline_review_decision(
        tmp_path,
        run_id=run_id,
        artifact_type="proposition",
        artifact_id="p-x",
        decision="approved",
        decision_id="prd-one",
        reason="y",
    )
    with pytest.raises(ValueError, match="already exists"):
        append_pipeline_review_decision(
            tmp_path,
            run_id=run_id,
            artifact_type="proposition",
            artifact_id="p-y",
            decision="rejected",
            decision_id="prd-one",
        )


def test_export_readback_pipeline_review_decisions(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    rid = str(bundle["run"]["id"])
    pid = str(bundle["propositions"][0]["id"])
    row = PipelineReviewDecision(
        id="prd-export-1",
        run_id=rid,
        artifact_type="proposition",
        artifact_id=pid,
        decision="approved",
        reviewed_at="2026-04-01T00:00:00Z",
        reason="lgtm",
    )
    bundle["pipeline_review_decisions"] = [row.model_dump(mode="json")]
    export_bundle(bundle, output_dir=str(tmp_path))
    loaded = load_exported_bundle(tmp_path)
    assert len(loaded.get("pipeline_review_decisions") or []) == 1
    assert loaded["pipeline_review_decisions"][0]["id"] == "prd-export-1"
    assert any(
        isinstance(a, dict) and a.get("artifact_type") == "pipeline_review_decisions"
        for a in (loaded.get("run_artifacts") or [])
    )
    raw = json.loads((tmp_path / "pipeline_review_decisions.json").read_text(encoding="utf-8"))
    assert raw[0]["decision"] == "approved"


def test_lint_warns_low_confidence_without_pipeline_review() -> None:
    bundle = build_demo_bundle(use_llm=False)
    rat = bundle["source_categorisation_rationales"][0]
    rat["confidence"] = "low"
    report = lint_bundle(bundle)
    aid = categorisation_artifact_id(rat)
    assert any(
        f"low-confidence categorisation without pipeline_review_decision: {aid}" in w
        for w in report["warnings"]
    )


def test_lint_warns_rejected_trace_without_proposition_override() -> None:
    bundle = build_demo_bundle(use_llm=False)
    trace = bundle["proposition_extraction_traces"][0]
    prop = next(p for p in bundle["propositions"] if p["id"] == trace["proposition_id"])
    tid = str(trace["id"])
    pid = str(prop["id"])
    bundle["pipeline_review_decisions"] = [
        {
            "id": "rej-1",
            "run_id": str(bundle["run"]["id"]),
            "artifact_type": "proposition_extraction_trace",
            "artifact_id": tid,
            "decision": "rejected",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "bad",
        }
    ]
    r1 = lint_bundle(bundle)
    assert any("rejected proposition_extraction_trace still used" in w for w in r1["warnings"])

    bundle["pipeline_review_decisions"].append(
        {
            "id": "app-1",
            "run_id": str(bundle["run"]["id"]),
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "approved",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "reason": "accept risk",
        }
    )
    r2 = lint_bundle(bundle)
    assert not any("rejected proposition_extraction_trace still used" in w for w in r2["warnings"])


def test_load_exported_bundle_without_pipeline_review_file(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_static_bundle(bundle=bundle, output_dir=str(tmp_path))
    (tmp_path / "pipeline_review_decisions.json").unlink(missing_ok=True)
    payload = load_exported_bundle(tmp_path)
    # Missing file normalises to an empty list (same as an empty on-disk export).
    assert payload.get("pipeline_review_decisions") == []
    assert lint_bundle(payload)["ok"] is True


def test_operations_list_pipeline_review_decisions(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    append_pipeline_review_decision(
        tmp_path,
        run_id=run_id,
        artifact_type="source_target_link",
        artifact_id="link-1",
        decision="needs_review",
        reason="check",
    )
    store = OperationalStore(export_dir=tmp_path)
    all_rows = store.list_pipeline_review_decisions(run_id=run_id)
    assert all_rows["count"] == 1
    filtered = store.list_pipeline_review_decisions(
        run_id=run_id,
        decision="needs_review",
    )
    assert filtered["count"] == 1
