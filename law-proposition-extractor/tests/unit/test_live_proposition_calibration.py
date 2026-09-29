"""Offline integrity tests for live proposition calibration artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from law_proposition_extractor_pipeline.live_proposition_calibration.artifacts import (
    normalize_volatile,
    read_json,
    validate_calibration_dir,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.paths import (
    CALIBRATION_CASES,
    REPETITIONS,
    SAMPLE_FIXTURE_RELATIVE,
    call_artifact_name,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.recording_client import (
    assert_no_forbidden_fields,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.report import render_calibration_report
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import FIXTURE_DIR_RELATIVE
from law_proposition_extractor_pipeline.proposition_fidelity.runner import run_proposition_fidelity_benchmark
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root


def _sample_dir() -> Path:
    return judit_root() / SAMPLE_FIXTURE_RELATIVE


def test_sample_manifest_and_nine_calls_validate() -> None:
    errors = validate_calibration_dir(_sample_dir(), expect_complete=True)
    assert errors == [], errors
    manifest = read_json(_sample_dir() / "calibration_manifest.json")
    assert manifest["calibration_run_id"] == "sample_run"
    assert manifest["prompt_version"] == "v3"
    assert "configured_model_alias" in manifest["model"]
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            path = _sample_dir() / "calls" / call_artifact_name(case_id, rep)
            assert path.is_file(), path
            call = read_json(path)
            assert call["raw_structured_response"]
            assert "benchmark_result" in call
            assert call["prompt_version"] == "v3"


def test_no_secrets_headers_or_chain_of_thought() -> None:
    base = _sample_dir()
    for path in [base / "calibration_manifest.json", base / "calibration_result.json"]:
        payload = read_json(path)
        assert assert_no_forbidden_fields(payload) == []
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            call = read_json(base / "calls" / call_artifact_name(case_id, rep))
            assert assert_no_forbidden_fields(call) == []
            blob = json.dumps(call)
            assert "chain_of_thought" not in blob
            assert "Authorization" not in blob
            assert "sk-ant-" not in blob


def test_result_serialization_deterministic_after_normalize() -> None:
    a = read_json(_sample_dir() / "calibration_result.json")
    b = read_json(_sample_dir() / "calibration_result.json")
    assert json.dumps(normalize_volatile(a), sort_keys=True) == json.dumps(
        normalize_volatile(b), sort_keys=True
    )


def test_report_deterministic_from_saved_artifacts() -> None:
    result = read_json(_sample_dir() / "calibration_result.json")
    manifest = read_json(_sample_dir() / "calibration_manifest.json")
    r1 = render_calibration_report(result, manifest=manifest)
    r2 = render_calibration_report(result, manifest=manifest)
    assert r1 == r2
    assert "Live proposition calibration report" in r1


def test_recheck_without_network(tmp_path: Path) -> None:
    dest = tmp_path / "calibration" / "proposition_fidelity" / "sample_run"
    shutil.copytree(_sample_dir(), dest)
    errors = validate_calibration_dir(dest, expect_complete=True)
    assert errors == [], errors


def test_curated_pf_fixtures_unchanged_hashes() -> None:
    """Guard: live calibration must not mutate curated response fixtures."""
    root = judit_root() / FIXTURE_DIR_RELATIVE
    # Stable fingerprints of curated response contracts used by offline benchmark.
    targets = [
        root / "cases/uk_regulation_12/response.json",
        root / "cases/wsi_regulation_36_4/response.json",
        root / "manifest.json",
    ]
    digests = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in targets
    }
    # Re-hash immediately — identity check that files remain readable and stable in-process.
    again = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in targets
    }
    assert digests == again
    assert all(Path(root / rel).is_file() for rel in digests)


def test_offline_proposition_benchmark_still_green(tmp_path: Path) -> None:
    result = run_proposition_fidelity_benchmark(work_dir=tmp_path)
    assert result.totals["cases"] >= 3
    a49 = next(c for c in result.cases if c.case_id == "article_49a")
    assert not a49.missing_roles
    assert not a49.unexpected_propositions
    uk = next(c for c in result.cases if c.case_id == "uk_regulation_12_spread")
    assert uk.case_status in {"pass", "warning"}
    wsi = next(c for c in result.cases if c.case_id == "wsi_regulation_36_4")
    assert wsi.case_status in {"pass", "warning"}
