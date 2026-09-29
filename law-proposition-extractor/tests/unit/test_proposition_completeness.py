"""Proposition completeness assessment (deterministic layer)."""

from pathlib import Path
import json

from fastapi.testclient import TestClient
from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_domain import (
    Cluster,
    Proposition,
    ReviewStatus,
    SourceRecord,
    Topic,
)
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import lint_bundle, load_exported_bundle
from law_proposition_extractor_pipeline.proposition_completeness import build_proposition_completeness_assessments
from law_proposition_extractor_pipeline.runner import _build_proposition_extraction_traces


def test_this_regulation_context_dependent_and_suggested_display() -> None:
    topic = Topic(id="t1", name="t")
    cluster = Cluster(id="c1", topic_id="t1", name="c")
    source = SourceRecord(
        id="src-reg",
        title="Retained EU Regulation 2016/429",
        jurisdiction="UK",
        citation="Retained EU Reg 2016/429",
        kind="regulation",
        authoritative_text="dummy",
        current_snapshot_id="s1",
        review_status=ReviewStatus.PROPOSED,
    )
    prop = Proposition(
        id="p-reg-1",
        topic_id=topic.id,
        cluster_id=cluster.id,
        source_record_id=source.id,
        source_snapshot_id=source.current_snapshot_id,
        jurisdiction="UK",
        proposition_text="This Regulation shall apply without prejudice to other provisions.",
        legal_subject="Regulation",
        action="applies",
    )
    traces = _build_proposition_extraction_traces(
        propositions=[prop],
        use_llm=False,
        extraction_prompt={"name": "extract.propositions.default", "version": "v1"},
        extraction_strategy_version="vtest",
        extraction_hook={"cache_status": None},
        pipeline_version="pvtest",
    )
    rows = build_proposition_completeness_assessments(
        propositions=[prop],
        proposition_extraction_traces=traces,
        source_records=[source],
    )
    assert len(rows) == 1
    a = rows[0]
    assert a.status == "context_dependent"
    assert "instrument_identity" in a.missing_context
    assert a.suggested_display_statement
    assert "Retained EU Reg 2016/429" in (a.suggested_display_statement or "")
    assert "This Regulation" not in (a.suggested_display_statement or "")


def test_structured_list_with_parent_context_not_fragmentary() -> None:
    text = """Article 109
1.
The Member States shall establish and maintain a computer database for recording of at least:
(a) the following information related to kept animals of the bovine species: bovine-specific details.
(b) the following information related to kept animals of the ovine species: ovine-specific details.
(d) the following information related to kept animals of the equine species:
(i) their unique code as provided for in Article 114.
"""
    source = SourceRecord(
        id="pilot-eu-2016-429-art109",
        title="Regulation (EU) 2016/429 — Article 109",
        jurisdiction="EU",
        citation="CELEX 32016R0429 Art 109",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="article:109",
        current_snapshot_id="snap-art109",
        review_status=ReviewStatus.PROPOSED,
        metadata={},
    )
    topic = Topic(id="topic-db", name="Database duties")
    cluster = Cluster(id="cluster-db", topic_id="topic-db", name="Core duties")
    from law_proposition_extractor_pipeline.extract import extract_propositions

    props = extract_propositions(
        source=source, topic=topic, cluster=cluster, limit=24, llm_client=None
    )
    equine = next(p for p in props if "equine" in p.proposition_text.lower())
    traces = _build_proposition_extraction_traces(
        propositions=[equine],
        use_llm=False,
        extraction_prompt={"name": "extract.propositions.default", "version": "v1"},
        extraction_strategy_version="vstructured-test",
        extraction_hook={"cache_status": None},
        pipeline_version="pipeline-test",
    )
    assert traces[0].signals.get("parent_context")
    rows = build_proposition_completeness_assessments(
        propositions=[equine],
        proposition_extraction_traces=traces,
        source_records=[source],
    )
    assert rows[0].status == "complete"


def test_cross_reference_only_fragmentary() -> None:
    topic = Topic(id="t1", name="t")
    cluster = Cluster(id="c1", topic_id="t1", name="c")
    source = SourceRecord(
        id="src-cr",
        title="Demo",
        jurisdiction="EU",
        citation="X",
        kind="regulation",
        authoritative_text="x",
        current_snapshot_id="s1",
        review_status=ReviewStatus.PROPOSED,
    )
    prop = Proposition(
        id="p-cr",
        topic_id=topic.id,
        cluster_id=cluster.id,
        source_record_id=source.id,
        source_snapshot_id=source.current_snapshot_id,
        jurisdiction="EU",
        proposition_text="See Article 5(2) of Directive 99/99/EC.",
        legal_subject="",
        action="",
    )
    traces = _build_proposition_extraction_traces(
        propositions=[prop],
        use_llm=False,
        extraction_prompt={"name": "extract.propositions.default", "version": "v1"},
        extraction_strategy_version="vtest",
        extraction_hook={"cache_status": None},
        pipeline_version="pvtest",
    )
    rows = build_proposition_completeness_assessments(
        propositions=[prop],
        proposition_extraction_traces=traces,
        source_records=[source],
    )
    assert rows[0].status == "fragmentary"
    assert "cross_reference" in rows[0].missing_context


def test_export_manifest_lint_api_old_bundle(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    assert (tmp_path / "proposition_completeness_assessments.json").exists()
    loaded = load_exported_bundle(tmp_path)
    assert isinstance(loaded.get("proposition_completeness_assessments"), list)
    root_m = Path(tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "has_proposition_completeness_assessments" in root_m

    report = lint_bundle(loaded)
    assert isinstance(report.get("warnings"), list)

    run_id = str(bundle["run"]["id"])
    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        r = client.get(
            "/ops/proposition-completeness-assessments",
            params={"run_id": run_id},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["run_id"] == run_id
        assert len(payload["proposition_completeness_assessments"]) == len(bundle["propositions"])
        f = client.get(
            "/ops/proposition-completeness-assessments",
            params={"run_id": run_id, "status": "complete"},
        )
        assert f.status_code == 200
        assert isinstance(f.json()["proposition_completeness_assessments"], list)
    finally:
        settings.operations_export_dir = previous_export_dir

    no_pca = tmp_path / "no-pca"
    no_pca.mkdir()
    export_bundle(build_demo_bundle(use_llm=False), output_dir=str(no_pca))
    for path in no_pca.rglob("*"):
        if path.is_file() and "completeness" in path.name.lower():
            path.unlink()
    run_art_path = no_pca / "run_artifacts.json"
    raw_ra = json.loads(run_art_path.read_text(encoding="utf-8"))
    filtered = [
        x for x in raw_ra if isinstance(x, dict) and x.get("artifact_type") != "proposition_completeness_assessments"
    ]
    run_art_path.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
    run_slug_dir = next((no_pca / "runs").iterdir(), None)
    if run_slug_dir and run_slug_dir.is_dir():
        nested_ra = run_slug_dir / "run-artifacts.json"
        if nested_ra.exists():
            raw_n = json.loads(nested_ra.read_text(encoding="utf-8"))
            filtered_n = [
                x
                for x in raw_n
                if isinstance(x, dict) and x.get("artifact_type") != "proposition_completeness_assessments"
            ]
            nested_ra.write_text(json.dumps(filtered_n, indent=2), encoding="utf-8")

    legacy_loaded = load_exported_bundle(no_pca)
    assert "proposition_completeness_assessments" not in legacy_loaded

    settings.operations_export_dir = str(no_pca)
    try:
        c2 = TestClient(app)
        rid = str(legacy_loaded["run"]["id"])
        empty_payload = c2.get("/ops/proposition-completeness-assessments", params={"run_id": rid}).json()
        assert empty_payload["proposition_completeness_assessments"] == []
    finally:
        settings.operations_export_dir = previous_export_dir
