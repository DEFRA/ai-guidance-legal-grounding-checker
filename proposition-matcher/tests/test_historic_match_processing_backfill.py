"""historic_match_processing_backfill_v1 — fail-closed reconstruction cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proposition_matcher.matching.historic_match_processing import (
    POLICY_VERSION,
    analyse_run,
    report_to_dict,
    validate_match_processing,
    write_backfill,
)
from proposition_matcher.matching.match_summary import summarise_guidance_proposition_match


def _match(law_id: str, relationship: str = "GROUNDED") -> dict:
    return {
        "law_proposition": {"id": law_id},
        "relationship": relationship,
        "confidence": "high",
        "explanation": "x",
        "correctness_score": 0.5,
    }


def _row(gp_id: str, matches: list[dict] | None = None, **extra) -> dict:
    row = {
        "id": gp_id,
        "url": "https://example.test/g",
        "proposition_text": f"text for {gp_id}",
        "matches": matches if matches is not None else [],
        "summary": "",
    }
    row.update(extra)
    return row


def _write_run(
    tmp: Path,
    results: list[dict],
    *,
    metrics: dict | None = None,
    survivors: dict | list | None = None,
    errors: dict | None = None,
    skips: list[str] | None = None,
    guidance_ids: list[str] | None = None,
) -> Path:
    run = tmp / "source"
    run.mkdir()
    (run / "results.json").write_text(json.dumps(results, indent=2))
    if metrics is not None:
        (run / "metrics.json").write_text(json.dumps(metrics, indent=2))
    if survivors is not None:
        (run / "survivors.json").write_text(json.dumps(survivors, indent=2))
    if errors is not None:
        (run / "proposition_errors.json").write_text(json.dumps(errors, indent=2))
    if skips is not None:
        (run / "proposition_skips.json").write_text(json.dumps(skips, indent=2))
    if guidance_ids is not None:
        (run / "guidance_proposition_ids.json").write_text(json.dumps(guidance_ids, indent=2))
    (run / "MODEL.md").write_text("# historic fixture\n")
    return run


def _by_id(analyses):
    return {a.guidance_proposition_id: a for a in analyses}


# ── Case 1: native processing preserved ───────────────────────────────────────


def test_case1_native_processing_preserved(tmp_path: Path):
    native = {"candidate_count": 3, "classification": "complete"}
    run = _write_run(tmp_path, [_row("g-1", [_match("prop:a")], match_processing=native)])
    report, analyses, out = analyse_run(run)
    a = analyses[0]
    assert a.analysis_status == "native"
    assert a.match_processing == native
    assert out[0]["match_processing"] == native
    assert "provenance" not in out[0]["match_processing"]
    assert report.native_count == 1


# ── Case 2: explicit successful non-empty processing ──────────────────────────


def test_case2_explicit_successful_non_empty(tmp_path: Path):
    matches = [_match("prop:a"), _match("prop:b", "UNGROUNDED")]
    run = _write_run(
        tmp_path,
        [_row("g-1", matches)],
        survivors={"g-1": ["prop:a", "prop:b"]},
        metrics={"group_rerank": {"errored": 0}},
    )
    _, analyses, out = analyse_run(run)
    a = analyses[0]
    assert a.analysis_status == "reconstructed"
    mp = a.match_processing
    assert mp["classification"] == "complete"
    assert mp["candidate_count"] == 2
    assert mp["provenance"]["policy_version"] == POLICY_VERSION
    assert "CANDIDATE_COUNT_FROM_SURVIVOR_LIST" in mp["provenance"]["evidence_codes"]
    assert out[0]["matches"] == matches


# ── Case 3: explicit successful zero candidates ────────────────────────────────


def test_case3_explicit_successful_zero_candidates(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [])],
        survivors={"g-1": []},
    )
    _, analyses, _ = analyse_run(run)
    mp = analyses[0].match_processing
    assert mp["classification"] == "complete"
    assert mp["candidate_count"] == 0
    assert "ZERO_SURVIVORS_RECORDED" in mp["provenance"]["evidence_codes"]


# ── Case 4: empty matches without evidence ────────────────────────────────────


def test_case4_empty_matches_without_evidence_ambiguous(tmp_path: Path):
    run = _write_run(tmp_path, [_row("g-1", [])])
    report, analyses, out = analyse_run(run)
    assert analyses[0].analysis_status == "ambiguous"
    assert "match_processing" not in out[0]
    assert report.production_backfill_eligible is False
    with pytest.raises(RuntimeError, match="not production-backfill eligible"):
        write_backfill(run, tmp_path / "dest")


# ── Case 5: non-empty matches without completion evidence ─────────────────────


def test_case5_non_empty_matches_without_completion_evidence(tmp_path: Path):
    run = _write_run(tmp_path, [_row("g-1", [_match("prop:a")])])
    report, analyses, out = analyse_run(run)
    assert analyses[0].analysis_status == "ambiguous"
    assert analyses[0].match_processing is None or "match_processing" not in out[0]
    assert "NON_EMPTY_MATCHES_WITHOUT_SURVIVOR_EVIDENCE" in analyses[0].evidence_codes
    assert report.production_backfill_eligible is False


# ── Case 6: only ungrounded, successful processing ────────────────────────────


def test_case6_only_ungrounded_successful_processing(tmp_path: Path):
    matches = [_match("prop:a", "UNGROUNDED"), _match("prop:b", "UNGROUNDED")]
    run = _write_run(
        tmp_path,
        [_row("g-1", matches)],
        survivors={"g-1": ["prop:a", "prop:b"]},
    )
    _, analyses, out = analyse_run(run)
    mp = analyses[0].match_processing
    assert mp["classification"] == "complete"
    assert mp["candidate_count"] == 2
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing=mp,
        matches=out[0]["matches"],
    )
    assert summary["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"


# ── Case 7: explicit proposition failure ──────────────────────────────────────


def test_case7_explicit_proposition_failure(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [])],
        survivors={"g-1": ["prop:a", "prop:b"]},
        errors={"g-1": {"failure_reason": "group_rerank_request_failed"}},
    )
    _, analyses, _ = analyse_run(run)
    mp = analyses[0].match_processing
    assert mp["classification"] == "failed"
    assert mp["failure_reason"] == "group_rerank_request_failed"
    assert mp["candidate_count"] == 2


# ── Case 8: partial processing ────────────────────────────────────────────────


def test_case8_partial_processing(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a")])],
        survivors={"g-1": ["prop:a", "prop:b", "prop:c"]},
    )
    _, analyses, _ = analyse_run(run)
    mp = analyses[0].match_processing
    assert mp["classification"] == "partial"
    assert mp["failure_reason"] == "not_all_candidates_classified"
    assert mp["candidate_count"] == 3


# ── Case 9: explicitly skipped proposition ────────────────────────────────────


def test_case9_explicitly_skipped(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _row("g-kept", [_match("prop:a")]),
            _row("g-skip", []),
        ],
        survivors={"g-kept": ["prop:a"]},
        skips=["g-skip"],
    )
    report, analyses, out = analyse_run(run)
    by = _by_id(analyses)
    assert by["g-skip"].match_processing["classification"] == "not_attempted"
    assert by["g-kept"].match_processing["classification"] == "complete"
    assert out[1]["match_processing"]["classification"] == "not_attempted"
    assert report.production_backfill_eligible is True


# ── Case 10: missing result with insufficient evidence ────────────────────────


def test_case10_missing_result_insufficient_evidence(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a")])],
        survivors={"g-1": ["prop:a"]},
        guidance_ids=["g-1", "g-missing"],
    )
    report, analyses, _ = analyse_run(run)
    by = _by_id(analyses)
    assert by["g-missing"].analysis_status == "ambiguous"
    assert "MISSING_RESULT_WITHOUT_SKIP_EVIDENCE" in by["g-missing"].evidence_codes
    assert report.production_backfill_eligible is False


# ── Case 11: run-level errors without proposition attribution ─────────────────


def test_case11_run_level_errors_unattributed(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a")]), _row("g-2", [])],
        survivors={"g-1": ["prop:a"], "g-2": []},
        metrics={
            "guidance_propositions": 2,
            "guidance_props_with_survivors": 1,
            "guidance_props_empty": 1,
            "group_rerank": {"errored": 3},
        },
    )
    report, analyses, _ = analyse_run(run)
    assert all(a.analysis_status == "ambiguous" for a in analyses)
    assert report.production_backfill_eligible is False
    assert any("without per-proposition" in w for w in report.warnings)


# ── Case 12: candidate-count semantic protection ──────────────────────────────


def test_case12_candidate_count_from_survivors_not_matches(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a"), _match("prop:b")])],
        survivors={"g-1": ["prop:a", "prop:b", "prop:c", "prop:d", "prop:e"]},
    )
    _, analyses, _ = analyse_run(run)
    mp = analyses[0].match_processing
    assert mp["candidate_count"] == 5
    assert mp["classification"] == "partial"


# ── Case 13: relationships untouched ──────────────────────────────────────────


def test_case13_relationships_untouched(tmp_path: Path):
    matches = [
        _match("prop:a", "CONFLICTS"),
        _match("prop:b", "GUIDANCE_BROADER"),
    ]
    run = _write_run(
        tmp_path,
        [_row("g-1", matches, summary="keep-me", content_id="cid")],
        survivors={"g-1": ["prop:a", "prop:b"]},
    )
    dest = tmp_path / "dest"
    write_backfill(run, dest)
    src = json.loads((run / "results.json").read_text())
    out = json.loads((dest / "results.json").read_text())
    for s, d in zip(src, out, strict=True):
        assert s["matches"] == d["matches"]
        assert s["summary"] == d["summary"]
        assert s["content_id"] == d["content_id"]
        assert s["id"] == d["id"]


# ── Case 14: source run unchanged ─────────────────────────────────────────────


def test_case14_source_run_unchanged(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a")])],
        survivors={"g-1": ["prop:a"]},
    )
    before = {p.name: p.read_bytes() for p in run.iterdir() if p.is_file()}
    write_backfill(run, tmp_path / "dest")
    after = {p.name: p.read_bytes() for p in run.iterdir() if p.is_file()}
    assert before == after


# ── Case 15: idempotence ──────────────────────────────────────────────────────


def test_case15_idempotence(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a")])],
        survivors={"g-1": ["prop:a"]},
    )
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    write_backfill(run, d1)
    write_backfill(run, d2)
    r1 = json.loads((d1 / "results.json").read_text())
    r2 = json.loads((d2 / "results.json").read_text())
    # Provenance is semantically identical excluding unavoidable timestamps (none used).
    assert r1 == r2
    rep1 = json.loads((d1 / "match_processing_backfill_report.json").read_text())
    rep2 = json.loads((d2 / "match_processing_backfill_report.json").read_text())
    assert rep1["propositions"] == rep2["propositions"]
    assert rep1["source_content_hash"] == rep2["source_content_hash"]


# ── Case 16: ambiguous run eligibility ────────────────────────────────────────


def test_case16_ambiguous_run_not_eligible(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _row("g-ok", [_match("prop:a")]),
            _row("g-amb", []),
        ],
        survivors={"g-ok": ["prop:a"]},  # g-amb has no survivors artefact entry
    )
    report, analyses, _ = analyse_run(run)
    by = _by_id(analyses)
    assert by["g-ok"].analysis_status == "reconstructed"
    assert by["g-amb"].analysis_status == "ambiguous"
    assert report.production_backfill_eligible is False
    assert "g-amb" in report.ambiguous_proposition_ids
    with pytest.raises(RuntimeError):
        write_backfill(run, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


# ── Case 17: mixed native and historic rows ───────────────────────────────────


def test_case17_mixed_native_and_historic(tmp_path: Path):
    native = {"candidate_count": 1, "classification": "complete"}
    run = _write_run(
        tmp_path,
        [
            _row("g-native", [_match("prop:a")], match_processing=dict(native)),
            _row("g-hist", [_match("prop:b")]),
        ],
        survivors={"g-hist": ["prop:b"]},
    )
    _, analyses, out = analyse_run(run)
    by = _by_id(analyses)
    assert by["g-native"].analysis_status == "native"
    assert by["g-hist"].analysis_status == "reconstructed"
    assert out[0]["match_processing"] == native
    assert out[1]["match_processing"]["provenance"]["origin"] == "historic_backfill"


# ── Case 18: invalid existing processing ──────────────────────────────────────


def test_case18_invalid_existing_processing(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _row(
                "g-bad",
                [_match("prop:a")],
                match_processing={"candidate_count": 1, "classification": "COMPLETE"},
            )
        ],
        survivors={"g-bad": ["prop:a"]},
    )
    report, analyses, out = analyse_run(run)
    assert analyses[0].analysis_status == "invalid_native"
    assert report.production_backfill_eligible is False
    assert out[0]["match_processing"]["classification"] == "COMPLETE"  # not overwritten
    with pytest.raises(RuntimeError):
        write_backfill(run, tmp_path / "dest")


# ── Case 19: provenance ───────────────────────────────────────────────────────


def test_case19_provenance_on_reconstructed_and_report(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [])],
        survivors={"g-1": []},
    )
    dest = tmp_path / "dest"
    report = write_backfill(run, dest)
    out = json.loads((dest / "results.json").read_text())
    prov = out[0]["match_processing"]["provenance"]
    assert prov["origin"] == "historic_backfill"
    assert prov["policy_version"] == POLICY_VERSION
    assert prov["evidence_codes"]
    assert prov["source_content_hash"].startswith("sha256:")
    assert (dest / "match_processing_backfill_report.json").exists()
    assert report_to_dict(report)["policy_version"] == POLICY_VERSION


# ── Case 20 helpers live partly in assembler tests; Matcher-side contract ─────


def test_case20_valid_reconstructed_round_trip_summary(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [_match("prop:a", "UNGROUNDED")])],
        survivors={"g-1": ["prop:a"]},
    )
    dest = tmp_path / "dest"
    write_backfill(run, dest)
    row = json.loads((dest / "results.json").read_text())[0]
    assert validate_match_processing(row["match_processing"]) == []
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing=row["match_processing"],
        matches=row["matches"],
    )
    assert summary["assessment_status"] == "COMPLETE"
    assert summary["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"


def test_metrics_empty_alignment_allows_zero_candidate_complete(tmp_path: Path):
    """Narrow production rule: empty-count metrics must align exactly."""
    results = [_row("g-empty", []), _row("g-hit", [_match("prop:a")])]
    run = _write_run(
        tmp_path,
        results,
        survivors={"g-hit": ["prop:a"]},  # empty row needs metrics alignment, not survivors
        metrics={
            "guidance_propositions": 2,
            "guidance_props_with_survivors": 1,
            "guidance_props_empty": 1,
            "group_rerank": {"errored": 0},
        },
    )
    report, analyses, _ = analyse_run(run)
    by = _by_id(analyses)
    assert by["g-empty"].match_processing["classification"] == "complete"
    assert by["g-empty"].match_processing["candidate_count"] == 0
    assert by["g-hit"].match_processing["classification"] == "complete"
    assert report.production_backfill_eligible is True


def test_refuse_overwrite_without_flag(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [])],
        survivors={"g-1": []},
    )
    dest = tmp_path / "dest"
    write_backfill(run, dest)
    with pytest.raises(FileExistsError):
        write_backfill(run, dest, overwrite=False)
    write_backfill(run, dest, overwrite=True)


def test_refuse_in_place_mutation(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [_row("g-1", [])],
        survivors={"g-1": []},
    )
    with pytest.raises(ValueError, match="in-place"):
        write_backfill(run, run)
