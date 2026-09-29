from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.cli import app as cli_app
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.effective_views import (
    find_original_artifact_in_bundle,
    resolve_effective_artifact_view,
)
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, load_exported_bundle
from law_proposition_extractor_pipeline.operations import OperationalStore
from law_proposition_extractor_pipeline.pipeline_reviews import (
    append_pipeline_review_decision,
    categorisation_artifact_id,
)
from typer.testing import CliRunner


def test_approved_decision_effective_status_only() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = bundle["propositions"][0]
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    decisions = [
        {
            "id": "prd-a",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "approved",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "ok",
        }
    ]
    view = resolve_effective_artifact_view(
        artifact_type="proposition",
        original_artifact=prop,
        pipeline_review_decisions=decisions,
    )
    assert view["effective_status"] == "approved"
    assert view["effective_value"] == view["original_artifact"]
    assert view["effective_value"]["proposition_text"] == prop["proposition_text"]


def test_overridden_decision_changes_effective_value() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = copy.deepcopy(bundle["propositions"][0])
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    original_text = str(prop["proposition_text"])
    decisions = [
        {
            "id": "prd-o",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "overridden",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "fix typo",
            "replacement_value": {"proposition_text": original_text + " [patched]"},
        }
    ]
    view = resolve_effective_artifact_view(
        artifact_type="proposition",
        original_artifact=prop,
        pipeline_review_decisions=decisions,
    )
    assert view["effective_status"] == "overridden"
    assert view["effective_value"]["proposition_text"] == original_text + " [patched]"
    assert view["original_artifact"]["proposition_text"] == original_text


def test_rejected_decision_does_not_change_effective_value() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = copy.deepcopy(bundle["propositions"][0])
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    decisions = [
        {
            "id": "prd-r",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "rejected",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "no",
        }
    ]
    view = resolve_effective_artifact_view(
        artifact_type="proposition",
        original_artifact=prop,
        pipeline_review_decisions=decisions,
    )
    assert view["effective_status"] == "rejected"
    assert view["effective_value"] == view["original_artifact"]


def test_superseded_decision_ignored() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = bundle["propositions"][0]
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    decisions = [
        {
            "id": "old",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "needs_review",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "",
        },
        {
            "id": "new",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "approved",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "reason": "",
            "supersedes_decision_id": "old",
        },
    ]
    view = resolve_effective_artifact_view(
        artifact_type="proposition",
        original_artifact=prop,
        pipeline_review_decisions=decisions,
    )
    assert view["current_review_decision"] is not None
    assert view["current_review_decision"]["id"] == "new"
    assert view["effective_status"] == "approved"


def test_find_original_artifact_source_inventory_row() -> None:
    bundle = build_demo_bundle(use_llm=False)
    inv = bundle["source_inventory"]
    assert isinstance(inv, dict)
    rows = inv.get("rows") or []
    row = rows[0]
    row_id = str(row["id"])
    found = find_original_artifact_in_bundle(
        bundle, artifact_type="source_inventory_row", artifact_id=row_id
    )
    assert found is not None
    assert str(found["id"]) == row_id


def test_lint_invalid_override_errors() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = bundle["propositions"][0]
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    bundle["pipeline_review_decisions"] = [
        {
            "id": "bad",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "overridden",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "",
            "replacement_value": {"proposition_text": 123},
        }
    ]
    r = lint_bundle(bundle)
    assert not r["ok"]
    assert any("invalid override replacement_value" in e for e in r["errors"])


def test_load_exported_bundle_graceful_no_decisions(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    loaded = load_exported_bundle(tmp_path)
    link = loaded["source_target_links"][0]
    decisions = loaded.get("pipeline_review_decisions") or []
    view = resolve_effective_artifact_view(
        artifact_type="source_target_link",
        original_artifact=link,
        pipeline_review_decisions=decisions,
    )
    assert view["effective_status"] == "generated"
    assert view["current_review_decision"] is None


def test_api_effective_endpoints(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        r = client.get("/ops/effective/propositions", params={"run_id": run_id})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        assert body["effective_propositions"][0]["effective_status"] == "generated"
        r2 = client.get(
            "/ops/effective/source-categorisation-rationales",
            params={"run_id": run_id},
        )
        assert r2.status_code == 200
        assert r2.json()["count"] >= 1
        r3 = client.get(
            "/ops/effective/proposition-extraction-traces",
            params={"run_id": run_id},
        )
        assert r3.status_code == 200
        assert r3.json()["count"] >= 1
    finally:
        settings.operations_export_dir = prev


def test_cli_effective_lists(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    runner = CliRunner()
    res = runner.invoke(
        cli_app,
        [
            "list-effective-source-target-links",
            "--export-dir",
            str(tmp_path),
            "--run-id",
            run_id,
        ],
    )
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["count"] >= 1
    assert payload["effective_source_target_links"][0]["effective_status"] == "generated"

    res2 = runner.invoke(
        cli_app,
        [
            "list-effective-source-categorisation-rationales",
            "--export-dir",
            str(tmp_path),
            "--run-id",
            run_id,
        ],
    )
    assert res2.exit_code == 0
    assert json.loads(res2.stdout)["count"] >= 1

    res3 = runner.invoke(
        cli_app,
        [
            "list-effective-proposition-extraction-traces",
            "--export-dir",
            str(tmp_path),
            "--run-id",
            run_id,
        ],
    )
    assert res3.exit_code == 0
    assert json.loads(res3.stdout)["count"] >= 1


def test_append_decision_reflected_in_effective_view(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    rat = bundle["source_categorisation_rationales"][0]
    aid = categorisation_artifact_id(rat)
    append_pipeline_review_decision(
        tmp_path,
        run_id=run_id,
        artifact_type="source_categorisation_rationale",
        artifact_id=aid,
        decision="approved",
        reason="checked",
    )
    store = OperationalStore(export_dir=tmp_path)
    views = store.list_effective_source_categorisation_rationales(run_id=run_id)
    match = next(
        v
        for v in views["effective_source_categorisation_rationales"]
        if v["artifact_id"] == aid
    )
    assert match["effective_status"] == "approved"
    assert match["review_reason"] == "checked"


def test_lint_warns_rejected_source_target_link_still_in_inventory() -> None:
    bundle = build_demo_bundle(use_llm=False)
    link = bundle["source_target_links"][0]
    lid = str(link["id"])
    rid = str(bundle["run"]["id"])
    bundle["pipeline_review_decisions"] = [
        {
            "id": "rej-link",
            "run_id": rid,
            "artifact_type": "source_target_link",
            "artifact_id": lid,
            "decision": "rejected",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "wrong",
        }
    ]
    r = lint_bundle(bundle)
    assert any(
        "effective view incomplete: rejected source_target_link" in w for w in r["warnings"]
    )


def test_mutating_effective_value_does_not_alter_original_artifact() -> None:
    bundle = build_demo_bundle(use_llm=False)
    prop = copy.deepcopy(bundle["propositions"][0])
    pid = str(prop["id"])
    rid = str(bundle["run"]["id"])
    decisions = [
        {
            "id": "prd-o",
            "run_id": rid,
            "artifact_type": "proposition",
            "artifact_id": pid,
            "decision": "overridden",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reason": "",
            "replacement_value": {"label": "from-review"},
        }
    ]
    view = resolve_effective_artifact_view(
        artifact_type="proposition",
        original_artifact=prop,
        pipeline_review_decisions=decisions,
    )
    view["effective_value"]["label"] = "mutated-after"
    assert view["original_artifact"]["label"] != "mutated-after"
    assert prop["label"] != "mutated-after"
