"""Offline saved-response replay for Article 49a triggered_by fix (20-BR10G)."""

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
from law_proposition_extractor_pipeline.live_proposition_calibration.replay_article_49a import (
    assert_article_49a_post_fix_replay,
    replay_article_49a_calibration_run,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

_LIVE_RUN = "live-pf-20260715T155907Z"


def _live_run_available() -> bool:
    return (judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN).is_dir()


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_saved_article_49a_live_replay_establishes_triggered_by(tmp_path: Path) -> None:
    # Fingerprint historical artifacts before replay.
    base = run_dir(_LIVE_RUN)
    historical_paths = [
        base / "calibration_result.json",
        base / "calibration_report.md",
        base / "calibration_manifest.json",
        *[
            calls_dir(_LIVE_RUN) / call_artifact_name("article_49a", rep)
            for rep in (1, 2, 3)
        ],
    ]
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }

    payload = replay_article_49a_calibration_run(
        _LIVE_RUN,
        write_result=True,
        work_dir=tmp_path,
    )
    assert_article_49a_post_fix_replay(payload)
    assert payload["model_calls_made"] == 0
    assert payload["historical_artifacts_modified"] is False
    assert (base / "post_fix_replay.json").is_file()

    after = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in historical_paths
        if p.is_file()
    }
    assert before == after

    for row in payload["repetitions"]:
        orig = row["original_live_calibration"]
        replay = row["post_fix_replay"]
        assert orig["triggered_by_count"] == 0
        assert replay["triggered_by_count"] == 1
        assert replay["exception_to_count"] == 3
        assert replay["proposition_count"] == 6
        assert len(replay["p3_trigger_condition_proposition_ids"]) == 3
        assert "Where the cases referred to in paragraph 2 apply" in (
            replay.get("p3_proposition_text") or ""
        )

    # Distinguish historical report from post-fix replay artifact.
    report = (base / "calibration_report.md").read_text(encoding="utf-8")
    assert "triggered_by" in report.lower() or "Article 49a" in report
    replay_doc = json.loads((base / "post_fix_replay.json").read_text(encoding="utf-8"))
    assert replay_doc["kind"] == "saved_response_replay_under_corrected_deterministic_code"
    assert replay_doc["distinguished_from"] == "original live calibration result"
