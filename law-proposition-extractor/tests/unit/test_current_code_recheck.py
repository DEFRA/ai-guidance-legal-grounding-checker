"""Complete current-code recheck of saved live proposition calibration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from law_proposition_extractor_pipeline.live_proposition_calibration.current_code_recheck import (
    assert_current_code_recheck,
    recheck_live_proposition_calibration,
    render_current_code_recheck_markdown,
)
from law_proposition_extractor_pipeline.live_proposition_calibration.paths import (
    CALIBRATION_CASES,
    REPETITIONS,
    call_artifact_name,
    calls_dir,
    run_dir,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

_LIVE_RUN = "live-pf-20260715T155907Z"


def _live_run_available() -> bool:
    return (judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN).is_dir()


def _historical_paths() -> list[Path]:
    base = run_dir(_LIVE_RUN)
    paths = [
        base / "calibration_result.json",
        base / "calibration_report.md",
        base / "calibration_manifest.json",
    ]
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            paths.append(calls_dir(_LIVE_RUN) / call_artifact_name(case_id, rep))
    return [p for p in paths if p.is_file()]


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_current_code_recheck_all_nine_repetitions(tmp_path: Path) -> None:
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in _historical_paths()}

    payload = recheck_live_proposition_calibration(
        _LIVE_RUN,
        write_result=True,
        work_dir=tmp_path,
    )
    assert_current_code_recheck(payload)

    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in _historical_paths()}
    assert before == after
    assert payload["model_calls_made"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["historical_artifacts_modified"] is False
    assert payload["totals"]["case_repetitions"] == 9

    base = run_dir(_LIVE_RUN)
    assert (base / "current_code_recheck.json").is_file()
    assert (base / "current_code_recheck.md").is_file()

    md = (base / "current_code_recheck.md").read_text(encoding="utf-8")
    assert "Historical live calibration" in md
    assert "Current-code saved-response recheck" in md
    assert "change origin" in md.lower() or "Change origin" in md or "| change origin |" in md


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_current_code_recheck_article_49a_action_and_triggers(tmp_path: Path) -> None:
    payload = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path
    )
    for rep in next(c for c in payload["cases"] if c["case_id"] == "article_49a")[
        "repetitions"
    ]:
        assert rep["historical_live_calibration"]["triggered_by_count"] == 0
        assert rep["replay"]["triggered_by_count"] == 1
        assert rep["p2"]["action_fidelity"]["status"] == "pass"
        assert rep["p2"]["action_fidelity"]["audit"]["detected_predicates"] == ["mix"]
        assert rep["p2"]["action_fidelity"]["audit"]["detected_polarity"] == "negative"
        hist_fails = rep["historical_live_calibration"]["failures"]
        assert any("action_fidelity" in f for f in hist_fails)


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_current_code_recheck_uk_regulation_12_one_proposition(tmp_path: Path) -> None:
    payload = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path
    )
    for rep in next(
        c for c in payload["cases"] if c["case_id"] == "uk_regulation_12_spread"
    )["repetitions"]:
        assert rep["historical_live_calibration"]["produced_count"] == 2
        assert rep["replay"]["proposition_count"] == 1
        assert rep["replay"]["measurement_basis_preserved"] is True
        assert rep["replay"]["threshold_10_metres_preserved"] is True


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_current_code_recheck_wsi_retains_expected_proposition(tmp_path: Path) -> None:
    payload = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path
    )
    for rep in next(
        c for c in payload["cases"] if c["case_id"] == "wsi_regulation_36_4"
    )["repetitions"]:
        assert "record-retention-calculations" in rep["evaluation"]["matched_roles"]
        assert rep["evaluation"]["unexpected_count"] == 0
        fails = [
            r
            for r in rep["evaluation"]["remaining_warnings_or_failures"]
            if r["status"] == "fail"
        ]
        assert fails == []


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_mutation_historical_calibration_result_not_overwritten(tmp_path: Path) -> None:
    base = run_dir(_LIVE_RUN)
    hist_path = base / "calibration_result.json"
    before = hist_path.read_bytes()
    recheck_live_proposition_calibration(_LIVE_RUN, write_result=True, work_dir=tmp_path)
    assert hist_path.read_bytes() == before
    # Sibling recheck artifacts exist and are distinct from historical.
    recheck = json.loads((base / "current_code_recheck.json").read_text(encoding="utf-8"))
    assert recheck["kind"].startswith("saved_response_replay")
    assert recheck["distinguished_from"] == "original live calibration result"


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_mutation_recheck_does_not_call_model(tmp_path: Path) -> None:
    network_hits: list[str] = []

    def _forbid_create(*_a: object, **_k: object) -> object:
        network_hits.append("chat.completions.create")
        raise AssertionError("current-code recheck must not call the model provider")

    with patch(
        "openai.resources.chat.completions.Completions.create",
        _forbid_create,
    ):
        payload = recheck_live_proposition_calibration(
            _LIVE_RUN, write_result=False, work_dir=tmp_path
        )
    assert network_hits == []
    assert payload["model_calls_made"] == 0
    assert_current_code_recheck(payload)


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_mutation_recheck_uses_original_not_edited_responses(tmp_path: Path) -> None:
    payload = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path
    )
    # Fingerprints in payload must match current on-disk call artifacts.
    for case_id in CALIBRATION_CASES:
        for rep in REPETITIONS:
            call = json.loads(
                (
                    calls_dir(_LIVE_RUN) / call_artifact_name(case_id, rep)
                ).read_text(encoding="utf-8")
            )
            expected = {
                hashlib.sha256(str(row.get("raw_response") or "").encode("utf-8")).hexdigest()
                for row in (call.get("provider_calls") or [])
                if isinstance(row, dict)
            }
            actual = {
                row["raw_response_sha256"]
                for row in payload["raw_response_fingerprints"]
                if row["case_id"] == case_id and row["repetition"] == rep
            }
            assert actual == expected


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_current_code_recheck_reproducible(tmp_path: Path) -> None:
    a = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path / "a"
    )
    b = recheck_live_proposition_calibration(
        _LIVE_RUN, write_result=False, work_dir=tmp_path / "b"
    )
    # Drop non-deterministic work_dir paths if any; compare semantic totals/statuses.
    def _compact(payload: dict) -> dict:
        return {
            "totals": payload["totals"],
            "change_table": payload["change_table"],
            "cases": [
                {
                    "case_id": c["case_id"],
                    "reps": [
                        {
                            "repetition": r["repetition"],
                            "case_status": r["evaluation"]["case_status"],
                            "produced": r["evaluation"]["produced_count"],
                            "matched": r["evaluation"]["matched_role_count"],
                            "unexpected": r["evaluation"]["unexpected_count"],
                            "replay_props": (r.get("replay") or {}).get("proposition_count"),
                            "triggered_by": (r.get("replay") or {}).get("triggered_by_count"),
                            "p2_action": ((r.get("p2") or {}).get("action_fidelity") or {}).get(
                                "status"
                            ),
                        }
                        for r in c["repetitions"]
                    ],
                }
                for c in payload["cases"]
            ],
        }

    assert _compact(a) == _compact(b)


def test_render_current_code_recheck_markdown_distinguishes_historical() -> None:
    md = render_current_code_recheck_markdown(
        {
            "calibration_run_id": "live-pf-test",
            "model_calls_made": 0,
            "network_calls_made": 0,
            "historical_artifacts_modified": False,
            "change_table": [
                {
                    "finding": "Article 49a P2 action fidelity",
                    "historical_result": "fail",
                    "current_code_result": "pass",
                    "change_origin": "structured action_expectation evaluator",
                }
            ],
            "cases": [],
            "remaining_inventory": [],
        }
    )
    assert "Historical live calibration" in md
    assert "Current-code saved-response recheck" in md
    assert "Article 49a P2 action fidelity" in md
