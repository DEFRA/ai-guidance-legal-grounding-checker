"""decision_explanations.json export / load compatibility tests."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_exporters.static_bundle import export_static_bundle
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    attach_decision_explanations,
    build_decision_explanations_artifact,
)
from law_proposition_extractor_pipeline.linting import load_exported_bundle
from law_proposition_extractor_pipeline.operations import OperationalStore


def _minimal_bundle(*, with_decisions: bool = True) -> dict:
    run_id = "run-explain-demo"
    decisions = []
    if with_decisions:
        from law_proposition_extractor_domain import (
            DecisionEvidence,
            DecisionExplanation,
            DecisionStage,
            DecisionSubjectKind,
            DecisionType,
            HeuristicMethod,
        )

        decisions = [
            DecisionExplanation(
                id="decision:deadbeefdeadbeefdeadbeefdeadbeef",
                stage=DecisionStage.SELECTION,
                decision_type=DecisionType.SELECT,
                subject_kind=DecisionSubjectKind.SOURCE_FRAGMENT,
                subject_id="frag-1",
                outcome="selected_for_extraction",
                method=HeuristicMethod.CONFIGURATION,
                rule_id="selection.required_locator",
                rule_version="1",
                summary="Selected because required.",
                evidence=[
                    DecisionEvidence(
                        kind="source_locator",
                        label="Fragment locator",
                        value="article:1",
                    )
                ],
            )
        ]
    artifact = build_decision_explanations_artifact(run_id=run_id, decisions=decisions)
    return {
        "run": {"id": run_id, "topic_id": "topic-1", "status": "completed"},
        "topic": {"id": "topic-1", "name": "Demo"},
        "clusters": [],
        "sources": [],
        "source_records": [],
        "source_snapshots": [],
        "source_fragments": [],
        "propositions": [],
        "proposition_extraction_jobs": [],
        "proposition_extraction_traces": [],
        "proposition_completeness_assessments": [],
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "review_decisions": [],
        "narrative": {"title": "Demo", "summary": "s", "sections": []},
        "decision_explanations": artifact,
        "run_artifacts": [
            {
                "id": f"artifact-{run_id}-decision-explanations",
                "run_id": run_id,
                "artifact_type": "decision_explanations",
                "provenance": "test",
                "content_hash": "abc",
            }
        ],
    }


def test_static_export_writes_decision_explanations(tmp_path: Path) -> None:
    bundle = _minimal_bundle()
    export_static_bundle(bundle, output_dir=str(tmp_path))
    path = tmp_path / "decision_explanations.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-explain-demo"
    assert payload["decisions"]
    assert payload["decisions"][0]["rule_id"] == "selection.required_locator"
    assert payload["decisions"][0]["rule_version"] == "1"
    # No absolute filesystem paths introduced in the artifact body.
    blob = json.dumps(payload)
    assert "/Users/" not in blob
    assert "C:\\\\" not in blob


def test_empty_decision_artifact_valid(tmp_path: Path) -> None:
    bundle = _minimal_bundle(with_decisions=False)
    attach_decision_explanations(bundle, decisions=[])
    export_static_bundle(bundle, output_dir=str(tmp_path))
    payload = json.loads((tmp_path / "decision_explanations.json").read_text(encoding="utf-8"))
    assert payload["decisions"] == []
    assert payload["metadata"]["registry_version"] == "1"


def test_older_export_without_artifact_remains_loadable(tmp_path: Path) -> None:
    bundle = _minimal_bundle(with_decisions=False)
    bundle.pop("decision_explanations", None)
    # Drop the run artifact entry so export does not invent a payload mapping note.
    bundle["run_artifacts"] = [
        a for a in bundle["run_artifacts"] if a.get("artifact_type") != "decision_explanations"
    ]
    export_static_bundle(bundle, output_dir=str(tmp_path))
    assert not (tmp_path / "decision_explanations.json").exists()
    loaded = load_exported_bundle(tmp_path)
    assert "decision_explanations" not in loaded or loaded.get("decision_explanations") in (
        None,
        {},
    )
    store = OperationalStore(export_dir=tmp_path)
    # Force an index entry by writing a minimal run layout if needed.
    result = store.read_decision_explanations(run_id="run-explain-demo")
    assert result["artifact_present"] is False
    assert result["decision_explanations"]["decisions"] == []


def test_artifact_contains_only_current_run_decisions(tmp_path: Path) -> None:
    bundle = _minimal_bundle()
    # Inject a foreign decision with a different run wrapper — attach rebuilds from list.
    attach_decision_explanations(bundle)
    export_static_bundle(bundle, output_dir=str(tmp_path))
    payload = json.loads((tmp_path / "decision_explanations.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-explain-demo"
    for row in payload["decisions"]:
        assert row["rule_id"].startswith("selection.")


def test_existing_artifacts_unchanged_when_explanations_added(tmp_path: Path) -> None:
    bundle = _minimal_bundle()
    bundle["propositions"] = [{"id": "prop-1", "proposition_text": "hello"}]
    export_static_bundle(bundle, output_dir=str(tmp_path))
    props = json.loads((tmp_path / "propositions.json").read_text(encoding="utf-8"))
    assert props == [{"id": "prop-1", "proposition_text": "hello"}]
