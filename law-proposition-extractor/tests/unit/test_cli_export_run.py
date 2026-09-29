"""CLI safety rails for export-run vs run-and-export-case."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from law_proposition_extractor_pipeline.cli import app
from law_proposition_extractor_pipeline.run_persistence import (
    assert_export_matches_source,
    build_persisted_run_config,
    export_mismatch_messages,
    persist_run_outputs,
    validate_rerun_extraction_allowed,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def _local_llm_bundle(*, proposition_count: int = 3) -> dict:
    props = [
        {
            "id": f"prop-{idx}",
            "topic_id": "topic-1",
            "cluster_id": "cluster-1",
            "source_record_id": "src-1",
            "text": f"Proposition {idx}",
            "display_label": f"P{idx}",
            "metadata": {},
        }
        for idx in range(proposition_count)
    ]
    return {
        "workflow_mode": "single_jurisdiction",
        "has_divergence_outputs": False,
        "topic": {"id": "topic-1", "name": "Test", "description": "", "subject_tags": []},
        "clusters": [{"id": "cluster-1", "topic_id": "topic-1", "name": "C", "description": ""}],
        "run": {"id": "run-001", "workflow_mode": "single_jurisdiction"},
        "source_records": [],
        "sources": [],
        "propositions": props,
        "divergence_assessments": [],
        "divergence_observations": [],
        "divergence_findings": [],
        "narrative": {"title": "T", "summary": "S", "sections": []},
        "stage_traces": [
            {
                "stage_name": "proposition extraction",
                "inputs": {
                    "extraction_mode": "local",
                    "extraction_mode_requested": "local",
                    "extraction_mode_effective": "local",
                    "derived_artifact_cache": {
                        "cache_dir": "/var/folders/xx/T/law-proposition-extractor/derived-artifacts",
                    },
                },
                "outputs": {},
            }
        ],
        "proposition_extraction_jobs": [{"attempted_llm_calls": 2, "successful_llm_calls": 1}],
        "extraction_llm_call_traces": [{"status": "ok"}],
    }


def _demo_case_payload() -> dict:
    case_path = _REPO_ROOT / "data/demo/example_case.json"
    if not case_path.is_file():
        pytest.skip("example_case.json missing")
    return json.loads(case_path.read_text(encoding="utf-8"))


def test_persist_run_outputs_writes_run_bundle_and_case_metadata(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=4)
    run_config = build_persisted_run_config(
        bundle=bundle,
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        case_data=case_data,
    )
    case_json = persist_run_outputs(
        output=tmp_path / "run-dir",
        case_data=case_data,
        bundle=bundle,
        run_config=run_config,
    )
    assert (tmp_path / "run-dir" / "run_bundle.json").is_file()
    assert (tmp_path / "run-dir" / "MODEL.md").is_file()
    stamped = json.loads(case_json.read_text(encoding="utf-8"))
    assert stamped["extraction"]["mode"] == "local"
    assert stamped["judit_run"]["extraction_mode_effective"] == "local"
    assert stamped["judit_run"]["proposition_count"] == 4


def test_export_run_exports_persisted_local_run_without_rerun(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=5)
    run_config = build_persisted_run_config(
        bundle=bundle,
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        case_data=case_data,
    )
    run_dir = tmp_path / "run-dir"
    case_json = persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=run_config,
    )
    out_dir = tmp_path / "export-out"
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        result = RUNNER.invoke(
            app,
            [
                "export-run",
                str(run_dir),
                "--output-dir",
                str(out_dir),
            ],
        )
    run_mock.assert_not_called()
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Exporting persisted run_bundle.json last modified at" in result.stdout
    assert "Derived cache directory" not in result.stdout
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["extraction_mode_effective"] == "local"
    assert manifest["proposition_count"] == 5
    props = json.loads((out_dir / "propositions.json").read_text(encoding="utf-8"))
    assert len(props) == 5


def test_export_run_verbose_shows_derived_cache_dir(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    cache_path = "/tmp/lpe-dcache-test"
    bundle = _local_llm_bundle(proposition_count=1)
    bundle["stage_traces"][0]["inputs"]["derived_artifact_cache"] = {
        "cache_dir": cache_path,
    }
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        result = RUNNER.invoke(
            app,
            [
                "export-run",
                str(run_dir),
                "--output-dir",
                str(tmp_path / "export-out"),
                "--verbose",
            ],
        )
    run_mock.assert_not_called()
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Derived cache directory" in result.stdout
    assert cache_path in result.stdout


def test_export_case_defaults_to_persisted_run_not_heuristic_rerun(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=6)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )
    out_dir = tmp_path / "export-out"
    with patch("law_proposition_extractor_pipeline.cli.run_case_file") as run_mock:
        result = RUNNER.invoke(
            app,
            [
                "export-case",
                str(run_dir / "case.json"),
                "--output-dir",
                str(out_dir),
                "--quiet",
            ],
        )
    run_mock.assert_not_called()
    assert result.exit_code == 0, result.stdout + result.stderr
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["extraction_mode_effective"] == "local"
    assert manifest["proposition_count"] == 6


def test_export_case_rerun_requires_explicit_extraction_mode(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=2)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )
    result = RUNNER.invoke(
        app,
        [
            "export-case",
            str(run_dir / "case.json"),
            "--rerun",
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert "explicit --extraction-mode" in result.stdout + result.stderr


def test_run_and_export_case_requires_explicit_mode_for_heuristic_rerun(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=2)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )
    result = RUNNER.invoke(
        app,
        [
            "run-and-export-case",
            str(run_dir / "case.json"),
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert "explicit --extraction-mode" in result.stdout + result.stderr


def test_run_and_export_case_allows_explicit_heuristic_rerun(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    bundle = _local_llm_bundle(proposition_count=2)
    run_dir = tmp_path / "run-dir"
    persist_run_outputs(
        output=run_dir,
        case_data=case_data,
        bundle=bundle,
        run_config=build_persisted_run_config(
            bundle=bundle,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            case_data=case_data,
        ),
    )
    heuristic_bundle = _local_llm_bundle(proposition_count=99)
    for tr in heuristic_bundle["stage_traces"]:
        tr["inputs"] = {
            "extraction_mode": "heuristic",
            "extraction_mode_requested": "heuristic",
            "extraction_mode_effective": "heuristic",
        }
    out_dir = tmp_path / "export-out"
    with patch("law_proposition_extractor_pipeline.cli.export_case_file") as export_mock:
        export_mock.return_value = heuristic_bundle
        result = RUNNER.invoke(
            app,
            [
                "run-and-export-case",
                str(run_dir / "case.json"),
                "--extraction-mode",
                "heuristic",
                "--output-dir",
                str(out_dir),
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    export_mock.assert_called_once()
    assert export_mock.call_args.kwargs["rerun"] is True
    assert export_mock.call_args.kwargs["extraction_mode"] == "heuristic"


def test_validate_rerun_requires_explicit_extraction_mode() -> None:
    persisted = build_persisted_run_config(
        bundle=_local_llm_bundle(proposition_count=1),
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        case_data={},
    )
    with pytest.raises(ValueError, match="explicit --extraction-mode"):
        validate_rerun_extraction_allowed(
            persisted=persisted,
            rerun=True,
            use_llm=False,
            extraction_mode=None,
            case_data={"extraction": {"mode": "local"}},
        )


def test_export_mismatch_guard_detects_mode_and_proposition_changes() -> None:
    source = _local_llm_bundle(proposition_count=3)
    exported = _local_llm_bundle(proposition_count=8)
    for tr in exported["stage_traces"]:
        tr["inputs"]["extraction_mode_effective"] = "heuristic"
        tr["inputs"]["extraction_mode"] = "heuristic"
    messages = export_mismatch_messages(source_bundle=source, exported_bundle=exported)
    assert any("extraction_mode" in msg for msg in messages)
    assert any("propositions" in msg for msg in messages)
    with pytest.raises(ValueError, match="Refusing to export"):
        assert_export_matches_source(source_bundle=source, exported_bundle=exported)


def test_export_case_refuses_run_directory_without_persisted_bundle(tmp_path: Path) -> None:
    case_data = _demo_case_payload()
    run_dir = tmp_path / "run-dir"
    run_dir.mkdir()
    (run_dir / "case.json").write_text(json.dumps(case_data, indent=2), encoding="utf-8")
    result = RUNNER.invoke(
        app,
        [
            "export-case",
            str(run_dir / "case.json"),
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert "run_bundle.json" in result.stdout + result.stderr


def test_export_case_help_documents_export_run_and_rerun() -> None:
    result = RUNNER.invoke(app, ["export-case", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "--rerun" in result.stdout
    assert "run_bundle.json" in result.stdout


def test_export_run_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["export-run", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "run_bundle.json" in result.stdout


def test_run_status_help_exits_zero() -> None:
    result = RUNNER.invoke(app, ["run-status", "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "run directory" in result.stdout.lower()


def test_run_bundle_persists_run_outputs(tmp_path: Path) -> None:
    bundle_path = tmp_path / "intake.json"
    bundle_path.write_text(
        json.dumps(
            {
                "bundle_id": "bundle-cli-test",
                "category_id": "cli_test_category",
                "created_at": "2026-06-01T00:00:00Z",
                "principal_sources": [
                    {
                        "source_id": "lex-cli-1",
                        "title": "Test Instrument One",
                        "source_type": "uksi",
                        "canonical_uri": "http://www.legislation.gov.uk/id/uksi/2020/1",
                        "relationship_to_category": "directly_regulates",
                        "review_status": "accepted",
                    }
                ],
                "amending_sources": [],
                "revocation_sources": [],
                "contextual_sources": [],
                "rejected_sources": [],
                "relationships": [],
                "metadata": {"intake": {"kind": "judit_intake", "filter_policy": {}}},
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "case-out"
    fake_bundle = _local_llm_bundle(proposition_count=7)
    progress_cm = MagicMock()
    progress_cm.__enter__.return_value = MagicMock()
    progress_cm.__exit__.return_value = False
    with (
        patch("law_proposition_extractor_pipeline.cli.pipeline_progress", return_value=progress_cm),
        patch("law_proposition_extractor_pipeline.cli.run_case_file", return_value=fake_bundle),
    ):
        result = RUNNER.invoke(
            app,
            [
                "run-bundle",
                str(bundle_path),
                "--output",
                str(out_dir),
                "--use-llm",
                "--extraction-mode",
                "local",
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out_dir / "run_bundle.json").is_file()
    stamped = json.loads((out_dir / "case.json").read_text(encoding="utf-8"))
    assert stamped["judit_run"]["extraction_mode_effective"] == "local"
    assert stamped["judit_run"]["proposition_count"] == 7
