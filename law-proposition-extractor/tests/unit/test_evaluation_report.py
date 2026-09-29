import json
from pathlib import Path

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.evaluation import (
    SCHEMA_VERSION,
    EvaluationReport,
    build_evaluation_report,
    render_evaluation_summary_md,
    write_evaluation_artifacts,
)
from law_proposition_extractor_pipeline.evaluation.document_breakdown import (
    compute_document_breakdown,
    extract_locator,
    extract_source_text,
    normalize_text_for_hash,
)
from law_proposition_extractor_pipeline.evaluation.output_volume import (
    classify_output_bucket,
    compute_output_volume,
    count_status_buckets,
    extract_status_classification,
)
from law_proposition_extractor_pipeline.export import export_bundle


def test_evaluation_report_to_dict_is_stable_and_serializable() -> None:
    report = EvaluationReport(
        schema_version=SCHEMA_VERSION,
        run_id="run-001",
        baseline_run_id=None,
        generated_at="2026-06-16T12:00:00Z",
        warnings=["example warning"],
    )
    payload = report.to_dict()
    serialized = json.dumps(payload, indent=2) + "\n"
    roundtrip = json.loads(serialized)

    assert roundtrip == payload
    assert payload["schema_version"] == "lpe-eval-v0.1"
    assert payload["run_id"] == "run-001"
    assert payload["baseline_run_id"] is None
    assert payload["comparison"] is None
    assert payload["document_breakdown"] == {}
    assert payload["warnings"] == ["example warning"]

    md = render_evaluation_summary_md(report)
    assert "deterministic Eval v0.1" in md
    assert "lpe-eval-v0.1" in md
    assert "LLM-as-judge" in md


def test_export_bundle_writes_evaluation_artefacts(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    run_id = bundle["run"]["id"]
    eval_dir = tmp_path / "runs" / run_id / "evaluation"
    json_path = eval_dir / "evaluation_report.json"
    md_path = eval_dir / "evaluation_summary.md"

    assert json_path.is_file()
    assert md_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["run_id"] == run_id
    assert payload["baseline_run_id"] is None
    assert payload["comparison"] is None
    assert isinstance(payload["generated_at"], str)

    md = md_path.read_text(encoding="utf-8")
    assert "deterministic Eval v0.1" in md


def test_build_evaluation_report_reads_run_id_from_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run-001"}),
        encoding="utf-8",
    )

    report = build_evaluation_report(run_dir)
    json_path, md_path = write_evaluation_artifacts(run_dir, report)

    assert report.run_id == "run-001"
    assert json_path.parent == run_dir / "evaluation"
    assert md_path.name == "evaluation_summary.md"
    assert "document_breakdown.missing_source_fragments" in report.warnings
    assert report.document_breakdown["fragment_count"] is None


def _write_source_fragment_artifact(run_dir: Path, export_root: Path, fragments: list[dict]) -> None:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_rel = "runs/run-001/artifacts/artifact-run-001-source-fragments.json"
    artifact_path = export_root / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(fragments, indent=2), encoding="utf-8")
    (run_dir / "run-artifacts.json").write_text(
        json.dumps(
            [
                {
                    "id": "artifact-run-001-source-fragments",
                    "artifact_type": "source_fragments",
                    "storage_uri": artifact_rel,
                }
            ]
        ),
        encoding="utf-8",
    )


def test_document_breakdown_normal_fragments_with_locators(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    fragments = [
        {
            "id": "frag-1",
            "locator": "article:10",
            "fragment_text": "Operators must maintain a movement register before dispatch.",
        },
        {
            "id": "frag-2",
            "locator": "article:11",
            "fragment_text": "The competent authority may inspect the register on request.",
        },
    ]
    _write_source_fragment_artifact(run_dir, export_root, fragments)

    report = build_evaluation_report(run_dir)
    breakdown = report.document_breakdown

    assert breakdown["fragment_count"] == 2
    assert breakdown["fragments_with_locator"] == 2
    assert breakdown["fragments_without_locator"] == 0
    assert breakdown["locator_coverage"] == 1.0
    assert breakdown["duplicate_fragment_hashes"] == 0
    assert breakdown["empty_or_tiny_fragments"] == 0
    assert breakdown["source_text_hash_mismatch_count"] is None
    assert "document_breakdown.missing_source_fragments" not in report.warnings

    md = render_evaluation_summary_md(report)
    assert "| Fragments | 2 |" in md
    assert "| Locator coverage | 100.0% |" in md


def test_document_breakdown_fragment_missing_locator(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    fragments = [
        {
            "id": "frag-1",
            "locator": "article:10",
            "fragment_text": "Operators must maintain a movement register before dispatch.",
        },
        {
            "id": "frag-2",
            "locator": "",
            "fragment_text": "The competent authority may inspect the register on request.",
        },
    ]
    _write_source_fragment_artifact(run_dir, export_root, fragments)

    report = build_evaluation_report(run_dir)
    breakdown = report.document_breakdown

    assert breakdown["fragment_count"] == 2
    assert breakdown["fragments_with_locator"] == 1
    assert breakdown["fragments_without_locator"] == 1
    assert breakdown["locator_coverage"] == 0.5
    assert "document_breakdown.low_locator_coverage" in report.warnings


def test_document_breakdown_duplicate_fragment_text(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    shared_text = "Operators must maintain a movement register before dispatch."
    fragments = [
        {"id": "frag-1", "locator": "article:10", "fragment_text": shared_text},
        {"id": "frag-2", "locator": "article:10a", "fragment_text": shared_text},
        {"id": "frag-3", "locator": "article:11", "fragment_text": shared_text},
        {
            "id": "frag-4",
            "locator": "article:12",
            "fragment_text": "The competent authority may inspect the register on request.",
        },
    ]
    _write_source_fragment_artifact(run_dir, export_root, fragments)

    report = build_evaluation_report(run_dir)
    breakdown = report.document_breakdown

    assert breakdown["duplicate_fragment_hashes"] == 2
    assert "document_breakdown.duplicate_fragments" in report.warnings


def test_document_breakdown_empty_or_tiny_fragment_text(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    fragments = [
        {
            "id": "frag-1",
            "locator": "article:10",
            "fragment_text": "Operators must maintain a movement register before dispatch.",
        },
        {"id": "frag-2", "locator": "article:11", "fragment_text": ""},
        {"id": "frag-3", "locator": "article:12", "fragment_text": "short text"},
    ]
    _write_source_fragment_artifact(run_dir, export_root, fragments)

    report = build_evaluation_report(run_dir)
    breakdown = report.document_breakdown

    assert breakdown["empty_or_tiny_fragments"] == 2
    assert "document_breakdown.empty_or_tiny_fragments" in report.warnings


def test_document_breakdown_no_source_fragment_data(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    run_dir.mkdir(parents=True)

    report = build_evaluation_report(run_dir)
    breakdown = report.document_breakdown

    assert breakdown["fragment_count"] is None
    assert breakdown["locator_coverage"] is None
    assert "document_breakdown.missing_source_fragments" in report.warnings

    md = render_evaluation_summary_md(report)
    assert "| Fragments | n/a |" in md


def test_document_breakdown_helpers_are_defensive() -> None:
    fragment = {"id": "frag-1", "metadata": {"source_locator": "regulation:1"}}
    assert extract_locator(fragment) == "regulation:1"
    assert extract_source_text({"fragment_text": "  hello   world  "}) == "  hello   world  "
    assert normalize_text_for_hash("  hello   world  ") == "hello world"

    assert compute_document_breakdown(None)["fragment_count"] is None
    assert compute_document_breakdown([])["fragment_count"] == 0


def test_export_bundle_populates_document_breakdown(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    run_id = bundle["run"]["id"]
    payload = json.loads(
        (tmp_path / "runs" / run_id / "evaluation" / "evaluation_report.json").read_text(
            encoding="utf-8"
        )
    )
    breakdown = payload["document_breakdown"]

    assert breakdown["fragment_count"] == len(bundle["source_fragments"])
    assert breakdown["fragments_with_locator"] == len(bundle["source_fragments"])
    assert breakdown["locator_coverage"] == 1.0
    assert "document_breakdown.missing_source_fragments" not in payload["warnings"]

    md = (tmp_path / "runs" / run_id / "evaluation" / "evaluation_summary.md").read_text(
        encoding="utf-8"
    )
    assert "## Document breakdown" in md
    assert "| Locator coverage | 100.0% |" in md


def _write_propositions_artifact(run_dir: Path, export_root: Path, propositions: list[dict]) -> None:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_rel = "runs/run-001/artifacts/artifact-run-001-propositions.json"
    artifact_path = export_root / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(propositions, indent=2), encoding="utf-8")
    existing = []
    run_artifacts_path = run_dir / "run-artifacts.json"
    if run_artifacts_path.is_file():
        existing = json.loads(run_artifacts_path.read_text(encoding="utf-8"))
    existing.append(
        {
            "id": "artifact-run-001-propositions",
            "artifact_type": "propositions",
            "storage_uri": artifact_rel,
        }
    )
    run_artifacts_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _write_beatrice_candidates(export_root: Path, candidates: list[dict]) -> None:
    export_root.mkdir(parents=True, exist_ok=True)
    (export_root / "proposition_matcher_law_candidates.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "run_id": "run-001",
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _sample_fragments() -> list[dict]:
    return [
        {
            "id": "frag-1",
            "locator": "article:10",
            "fragment_text": "Operators must maintain a movement register before dispatch.",
        },
        {
            "id": "frag-2",
            "locator": "article:11",
            "fragment_text": "The competent authority may inspect the register on request.",
        },
    ]


def _sample_propositions() -> list[dict]:
    return [
        {"id": "prop-1", "proposition_text": "Maintain a register."},
        {"id": "prop-2", "proposition_text": "Authority may inspect."},
        {"id": "prop-3", "proposition_text": "Keep records for five years."},
    ]


def _sample_beatrice_candidates() -> list[dict]:
    return [
        {"id": "bcand-1", "candidate_status": "ready"},
        {"id": "bcand-2", "candidate_status": "usable_with_context"},
        {"id": "bcand-3", "candidate_status": "needs_review"},
        {"id": "bcand-4", "candidate_status": "needs_review"},
    ]


def test_output_volume_normal_run_with_mixed_statuses(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_propositions_artifact(run_dir, export_root, _sample_propositions())
    _write_beatrice_candidates(export_root, _sample_beatrice_candidates())

    report = build_evaluation_report(run_dir)
    volume = report.output_volume

    assert volume["candidate_count"] == 3
    assert volume["final_statement_count"] == 4
    assert volume["ready_count"] == 1
    assert volume["usable_with_context_count"] == 1
    assert volume["needs_review_count"] == 2
    assert volume["candidates_per_fragment"] == 1.5
    assert volume["statements_per_fragment"] == 2.0
    assert "output_volume.missing_candidates" not in report.warnings
    assert "output_volume.missing_final_outputs" not in report.warnings
    assert "output_volume.review_load_exceeds_ready" in report.warnings

    md = render_evaluation_summary_md(report)
    assert "## Output volume" in md
    assert "| Candidates | 3 |" in md
    assert "| Final statements | 4 |" in md
    assert "| Ready | 1 |" in md
    assert "| Usable with context | 1 |" in md
    assert "| Needs review | 2 |" in md
    assert "| Candidates / fragment | 1.50 |" in md
    assert "| Statements / fragment | 2.00 |" in md


def test_output_volume_missing_candidate_artifact(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_beatrice_candidates(export_root, _sample_beatrice_candidates())

    report = build_evaluation_report(run_dir)
    volume = report.output_volume

    assert volume["candidate_count"] is None
    assert volume["final_statement_count"] == 4
    assert volume["candidates_per_fragment"] is None
    assert "output_volume.missing_candidates" in report.warnings


def test_output_volume_missing_final_output_artifact(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_propositions_artifact(run_dir, export_root, _sample_propositions())

    report = build_evaluation_report(run_dir)
    volume = report.output_volume

    assert volume["candidate_count"] == 3
    assert volume["final_statement_count"] is None
    assert volume["ready_count"] is None
    assert volume["usable_with_context_count"] is None
    assert volume["needs_review_count"] is None
    assert volume["statements_per_fragment"] is None
    assert "output_volume.missing_final_outputs" in report.warnings


def test_output_volume_zero_candidates_with_fragments(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_propositions_artifact(run_dir, export_root, [])

    report = build_evaluation_report(run_dir)
    volume = report.output_volume

    assert volume["candidate_count"] == 0
    assert volume["candidates_per_fragment"] == 0.0
    assert "output_volume.zero_candidates" in report.warnings


def test_output_volume_zero_final_outputs_with_candidates(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_propositions_artifact(run_dir, export_root, _sample_propositions())
    _write_beatrice_candidates(export_root, [])

    report = build_evaluation_report(run_dir)
    volume = report.output_volume

    assert volume["candidate_count"] == 3
    assert volume["final_statement_count"] == 0
    assert volume["statements_per_fragment"] == 0.0
    assert "output_volume.zero_final_outputs" in report.warnings


def test_output_volume_per_fragment_ratios_use_document_breakdown(tmp_path: Path) -> None:
    export_root = tmp_path
    run_dir = export_root / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    _write_source_fragment_artifact(run_dir, export_root, _sample_fragments())
    _write_propositions_artifact(run_dir, export_root, _sample_propositions())
    _write_beatrice_candidates(export_root, _sample_beatrice_candidates()[:1])

    report = build_evaluation_report(run_dir)

    assert report.document_breakdown["fragment_count"] == 2
    assert report.output_volume["candidates_per_fragment"] == 1.5
    assert report.output_volume["statements_per_fragment"] == 0.5


def test_output_volume_helpers_are_defensive() -> None:
    assert extract_status_classification({"candidate_status": "ready"}) == "ready"
    assert classify_output_bucket({"candidate_status": "usable_with_context"}) == "usable_with_context"
    assert classify_output_bucket({"candidate_status": "needs_review"}) == "needs_review"
    assert classify_output_bucket({"is_compliance_relevant": True}) == "ready"
    assert classify_output_bucket({"statement_text": "No status here."}) is None

    buckets = count_status_buckets(
        [
            {"candidate_status": "ready"},
            {"candidate_status": "needs_review"},
        ]
    )
    assert buckets == {
        "ready_count": 1,
        "usable_with_context_count": 0,
        "needs_review_count": 1,
    }
    assert count_status_buckets([{"statement_text": "No status"}]) == {
        "ready_count": None,
        "usable_with_context_count": None,
        "needs_review_count": None,
    }

    empty = compute_output_volume(candidates=None, final_outputs=None, fragment_count=2)
    assert empty["candidate_count"] is None
    assert empty["final_statement_count"] is None
    assert empty["candidates_per_fragment"] is None


def test_export_bundle_populates_output_volume(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    run_id = bundle["run"]["id"]
    payload = json.loads(
        (tmp_path / "runs" / run_id / "evaluation" / "evaluation_report.json").read_text(
            encoding="utf-8"
        )
    )
    volume = payload["output_volume"]

    assert volume["candidate_count"] == len(bundle["propositions"])
    assert isinstance(volume["final_statement_count"], int)
    assert volume["final_statement_count"] > 0
    assert isinstance(volume["ready_count"], int)
    assert "output_volume.missing_candidates" not in payload["warnings"]
    assert "output_volume.missing_final_outputs" not in payload["warnings"]

    md = (tmp_path / "runs" / run_id / "evaluation" / "evaluation_summary.md").read_text(
        encoding="utf-8"
    )
    assert "## Output volume" in md
    assert "| Candidates |" in md
    assert "| Final statements |" in md
