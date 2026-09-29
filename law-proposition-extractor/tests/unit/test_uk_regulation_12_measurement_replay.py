"""Offline saved-response replay for UK regulation 12 measurement fix (20-BR10H)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.live_proposition_calibration.paths import (
    call_artifact_name,
    calls_dir,
    run_dir,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.replay_uk_regulation_12 import (
    assert_uk_regulation_12_post_fix_replay,
    replay_uk_regulation_12_calibration_run,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

_LIVE_RUN = "live-pf-20260715T155907Z"


def _live_run_available() -> bool:
    return (judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN).is_dir()


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_saved_uk_regulation_12_live_replay_suppresses_measurement(tmp_path: Path) -> None:
    base = run_dir(_LIVE_RUN)
    historical_paths = [
        base / "calibration_result.json",
        base / "calibration_report.md",
        base / "calibration_manifest.json",
        *[
            calls_dir(_LIVE_RUN) / call_artifact_name("uk_regulation_12_spread", rep)
            for rep in (1, 2, 3)
        ],
    ]
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }

    payload = replay_uk_regulation_12_calibration_run(
        _LIVE_RUN,
        write_result=True,
        work_dir=tmp_path,
    )
    assert_uk_regulation_12_post_fix_replay(payload)
    assert payload["model_calls_made"] == 0
    assert payload["historical_artifacts_modified"] is False
    assert (base / "uk_regulation_12_post_fix_replay.json").is_file()

    after = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }
    assert before == after

    for row in payload["repetitions"]:
        orig = row["original_live_calibration"]
        replay = row["post_fix_replay"]
        assert orig["proposition_count"] == 2
        assert orig["unexpected_count"] == 1
        assert replay["proposition_count"] == 1
        assert replay["unexpected_count"] == 0
        assert replay["has_organic_manure_spread_prohibition"] is True
        assert replay["threshold_10_metres_preserved"] is True
        assert replay["measurement_basis_preserved"] is True
        assert replay["evidence_grounded"] is True

    # Distinguish historical report from post-fix replay artifact.
    report = (base / "calibration_report.md").read_text(encoding="utf-8")
    assert "uk_regulation_12" in report or "Regulation 12" in report
    replay_doc = json.loads(
        (base / "uk_regulation_12_post_fix_replay.json").read_text(encoding="utf-8")
    )
    assert replay_doc["kind"] == "saved_response_replay_under_corrected_deterministic_code"
    assert replay_doc["distinguished_from"] == "original live calibration result"
    assert "dependent qualification" in replay_doc["classification_note"].lower()


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_three_live_repetitions_semantically_equivalent_extra_rows() -> None:
    texts: list[str] = []
    for rep in (1, 2, 3):
        call = json.loads(
            (
                calls_dir(_LIVE_RUN)
                / call_artifact_name("uk_regulation_12_spread", rep)
            ).read_text(encoding="utf-8")
        )
        rows = call.get("raw_rows") or []
        assert len(rows) == 2
        extra = rows[1]["proposition_text"]
        texts.append(extra)
        assert "measured from the edge" in extra.lower()
        assert "10" in extra
    # Semantically equivalent across repetitions (allow minor subject paraphrase).
    assert all("edge of the surface water" in t.lower() for t in texts)
