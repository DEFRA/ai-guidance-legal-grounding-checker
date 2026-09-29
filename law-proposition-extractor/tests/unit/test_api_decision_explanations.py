"""API routes for decision explanations and heuristic registry definitions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.heuristics.registry import REGISTRY_VERSION, list_heuristics
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    attach_decision_explanations,
    build_decision_explanations_artifact,
)
from law_proposition_extractor_domain import (
    DecisionExplanation,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
)


def _sample_decision() -> DecisionExplanation:
    return DecisionExplanation(
        id="decision:demo0001",
        stage=DecisionStage.SELECTION,
        decision_type=DecisionType.SELECT,
        subject_kind=DecisionSubjectKind.SOURCE_FRAGMENT,
        subject_id="frag-demo",
        outcome="selected_for_extraction",
        method=HeuristicMethod.CONFIGURATION,
        rule_id="selection.required_locator",
        rule_version="1",
        summary="Selected because required.",
        metadata={"source_fragment_id": "frag-demo"},
    )


def test_decision_explanations_route_returns_active_run_artifact(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    run_id = str(bundle["run"]["id"])
    sample = _sample_decision()
    artifact = build_decision_explanations_artifact(run_id=run_id, decisions=[sample])
    assert artifact["decisions"]
    # Replace with a known single decision so the route is not coupled to demo size.
    attach_decision_explanations(bundle, decisions=[sample])
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    (tmp_path / "decision_explanations.json").write_text(
        json.dumps(artifact, indent=2),
        encoding="utf-8",
    )

    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/ops/decision-explanations", params={"run_id": run_id})
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == run_id
        assert payload["artifact_present"] is True
        assert payload["decision_count"] >= 1
        decisions = payload["decision_explanations"]["decisions"]
        by_id = {row["id"]: row for row in decisions}
        assert sample.id in by_id
        assert by_id[sample.id]["rule_id"] == "selection.required_locator"
        assert by_id[sample.id]["rule_version"] == "1"
        assert by_id[sample.id]["method"] == "configuration"
        assert by_id[sample.id]["metadata"]["source_fragment_id"] == "frag-demo"
        dumped = json.dumps(payload)
        assert "file://" not in dumped
        assert str(tmp_path) not in dumped
    finally:
        settings.operations_export_dir = previous


def test_decision_explanations_route_soft_missing_optional_artifact(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    # Ensure no decision_explanations attachment.
    bundle.pop("decision_explanations", None)
    if isinstance(bundle.get("run_artifacts"), list):
        bundle["run_artifacts"] = [
            row
            for row in bundle["run_artifacts"]
            if not (isinstance(row, dict) and row.get("artifact_type") == "decision_explanations")
        ]
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    # Remove file if export still wrote an empty one.
    path = tmp_path / "decision_explanations.json"
    if path.exists():
        path.unlink()

    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/ops/decision-explanations", params={"run_id": run_id})
        assert response.status_code == 200
        payload = response.json()
        assert payload["artifact_present"] is False
        assert payload["decision_count"] == 0
        assert payload["decision_explanations"]["decisions"] == []
        assert payload["decision_explanations"]["metadata"].get("missing_artifact") is True
    finally:
        settings.operations_export_dir = previous


def test_heuristics_route_deterministic_registry_order_and_versions() -> None:
    client = TestClient(app)
    response = client.get("/ops/heuristics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["registry_version"] == REGISTRY_VERSION
    assert payload["referenced_only"] is False
    heuristics = payload["heuristics"]
    assert heuristics
    rule_ids = [row["rule_id"] for row in heuristics]
    assert rule_ids == sorted(rule_ids)
    registered = {h.rule_id: h for h in list_heuristics()}
    assert len(heuristics) == len(registered)
    for row in heuristics:
        expected = registered[row["rule_id"]]
        assert row["version"] == expected.version
        assert row["name"] == expected.name
        assert row["plain_english_summary"] == expected.plain_english_summary
        assert row["method"] == expected.method.value
        for ref in row["code_references"]:
            assert not str(ref).startswith("file://")
            assert "/Users/" not in str(ref)


def test_heuristics_route_referenced_only_filters_to_run_rules(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    run_id = str(bundle["run"]["id"])
    sample = _sample_decision()
    attach_decision_explanations(bundle, decisions=[sample])
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    # Pin the exported artifact to the single sample decision (demo export may
    # otherwise retain pipeline-emitted decisions depending on export path).
    (tmp_path / "decision_explanations.json").write_text(
        json.dumps(
            build_decision_explanations_artifact(run_id=run_id, decisions=[sample]),
            indent=2,
        ),
        encoding="utf-8",
    )

    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        response = client.get(
            "/ops/heuristics",
            params={"run_id": run_id, "referenced_only": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["referenced_only"] is True
        assert payload["run_id"] == run_id
        rule_ids = {row["rule_id"] for row in payload["heuristics"]}
        assert rule_ids == {"selection.required_locator"}
    finally:
        settings.operations_export_dir = previous


def test_decision_and_heuristics_routes_do_not_invoke_production_heuristics(
    tmp_path: Path,
) -> None:
    bundle = build_demo_bundle(use_llm=False)
    run_id = str(bundle["run"]["id"])
    attach_decision_explanations(bundle, decisions=[_sample_decision()])
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        with (
            patch(
                "law_proposition_extractor_pipeline.heuristics.selection_explanations.build_selection_decision_explanations"
            ) as sel,
            patch(
                "law_proposition_extractor_pipeline.heuristics.classification_explanations.build_classification_decision_explanations"
            ) as clas,
            patch(
                "law_proposition_extractor_pipeline.heuristics.effective_law_explanations.build_effective_law_decision_explanations"
            ) as eff,
        ):
            r1 = client.get("/ops/decision-explanations", params={"run_id": run_id})
            r2 = client.get("/ops/heuristics", params={"run_id": run_id})
            assert r1.status_code == 200
            assert r2.status_code == 200
            sel.assert_not_called()
            clas.assert_not_called()
            eff.assert_not_called()
    finally:
        settings.operations_export_dir = previous


def test_older_runs_remain_accessible_without_decision_artifact(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle.pop("decision_explanations", None)
    if isinstance(bundle.get("run_artifacts"), list):
        bundle["run_artifacts"] = [
            row
            for row in bundle["run_artifacts"]
            if not (isinstance(row, dict) and row.get("artifact_type") == "decision_explanations")
        ]
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    path = tmp_path / "decision_explanations.json"
    if path.exists():
        path.unlink()

    previous = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        statements = client.get("/ops/effective-law-statements", params={"run_id": run_id})
        decisions = client.get("/ops/decision-explanations", params={"run_id": run_id})
        assert statements.status_code == 200
        assert decisions.status_code == 200
        assert decisions.json()["artifact_present"] is False
    finally:
        settings.operations_export_dir = previous
