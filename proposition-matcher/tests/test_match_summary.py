"""Proposition-level match summary derivation (pair relationship stays separate)."""

from proposition_matcher.matching.match_summary import (
    classify_processing,
    distinct_matches_by_law_id,
    summarise_guidance_proposition_match,
    summarise_guidance_propositions,
)


def _match(law_id: str, relationship: str) -> dict:
    return {
        "law_proposition": {"id": law_id},
        "relationship": relationship,
        "confidence": "high",
        "explanation": "x",
        "correctness_score": 0.5,
    }


def test_case1_reportable_grounded():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 1, "classification": "complete"},
        matches=[_match("prop:a", "GROUNDED")],
    )
    assert summary["assessment_status"] == "COMPLETE"
    assert summary["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert summary["reportable_comparison_count"] == 1
    assert summary["candidate_count"] == 1


def test_case2_multiple_reportable_hits_counted_without_collapsing_pairs():
    matches = [
        _match("prop:a", "GROUNDED"),
        _match("prop:b", "CONFLICTS"),
        _match("prop:c", "GUIDANCE_INCOMPLETE"),
        _match("prop:d", "GUIDANCE_BROADER"),
    ]
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 4, "classification": "complete"},
        matches=matches,
    )
    assert summary["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert summary["reportable_comparison_count"] == 4
    assert len(matches) == 4  # pair rows remain distinct


def test_case3_mixed_reportable_and_ungrounded():
    matches = [
        _match("prop:a", "GROUNDED"),
        _match("prop:b", "UNGROUNDED"),
    ]
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 2, "classification": "complete"},
        matches=matches,
    )
    assert summary["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert summary["reportable_comparison_count"] == 1
    assert summary["ungrounded_candidate_count"] == 1
    assert matches[1]["relationship"] == "UNGROUNDED"  # audit pair retained


def test_case4_only_ungrounded_candidates():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 2, "classification": "complete"},
        matches=[_match("prop:a", "UNGROUNDED"), _match("prop:b", "UNGROUNDED")],
    )
    assert summary["assessment_status"] == "COMPLETE"
    assert summary["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert summary["reportable_comparison_count"] == 0
    assert summary["ungrounded_candidate_count"] == 2


def test_case5_no_candidates_found():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 0, "classification": "complete"},
        matches=[],
    )
    assert summary["assessment_status"] == "COMPLETE"
    assert summary["coverage_result"] == "NO_CANDIDATES_FOUND"
    assert summary["candidate_count"] == 0


def test_case6_not_checked_must_not_be_no_candidates():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing=None,
        matches=[],
    )
    assert summary["assessment_status"] == "NOT_CHECKED"
    assert summary["coverage_result"] is None

    skipped = summarise_guidance_proposition_match(
        guidance_proposition_id="g-2",
        match_processing={"candidate_count": 0, "classification": "not_attempted"},
        matches=[],
    )
    assert skipped["assessment_status"] == "NOT_CHECKED"
    assert skipped["coverage_result"] is None


def test_case7_failed_must_not_get_conclusive_coverage():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={
            "candidate_count": 3,
            "classification": "failed",
            "failure_reason": "group_rerank_request_failed",
        },
        matches=[],
    )
    assert summary["assessment_status"] == "FAILED"
    assert summary["coverage_result"] is None
    assert summary["failure_reason"] == "group_rerank_request_failed"
    assert summary["coverage_result"] != "NO_CANDIDATES_FOUND"
    assert summary["coverage_result"] != "ONLY_UNGROUNDED_CANDIDATES"


def test_case8_partial_must_not_get_conclusive_coverage():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={
            "candidate_count": 3,
            "classification": "partial",
            "failure_reason": "not_all_candidates_classified",
        },
        matches=[_match("prop:a", "UNGROUNDED")],
    )
    assert summary["assessment_status"] == "PARTIAL"
    assert summary["coverage_result"] is None
    assert summary["ungrounded_candidate_count"] == 1


def test_case9_one_summary_per_guidance_proposition_in_scope():
    ids = ["g-reportable", "g-ungrounded", "g-empty", "g-unchecked", "g-failed", "g-partial"]
    entries = {
        "g-reportable": {
            "match_processing": {"candidate_count": 1, "classification": "complete"},
            "matches": [_match("prop:a", "GROUNDED")],
        },
        "g-ungrounded": {
            "match_processing": {"candidate_count": 1, "classification": "complete"},
            "matches": [_match("prop:b", "UNGROUNDED")],
        },
        "g-empty": {
            "match_processing": {"candidate_count": 0, "classification": "complete"},
            "matches": [],
        },
        "g-unchecked": {"matches": []},
        "g-failed": {
            "match_processing": {"candidate_count": 2, "classification": "failed"},
            "matches": [],
        },
        "g-partial": {
            "match_processing": {"candidate_count": 2, "classification": "partial"},
            "matches": [_match("prop:c", "GROUNDED")],
        },
    }
    summaries = summarise_guidance_propositions(ids, entries)
    assert [s["guidance_proposition_id"] for s in summaries] == ids
    by_id = {s["guidance_proposition_id"]: s for s in summaries}
    assert by_id["g-reportable"]["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert by_id["g-ungrounded"]["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert by_id["g-empty"]["coverage_result"] == "NO_CANDIDATES_FOUND"
    assert by_id["g-unchecked"]["assessment_status"] == "NOT_CHECKED"
    assert by_id["g-failed"]["assessment_status"] == "FAILED"
    assert by_id["g-partial"]["assessment_status"] == "PARTIAL"


def test_conflict_singular_counts_as_reportable():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 1, "classification": "complete"},
        matches=[_match("prop:a", "CONFLICT")],
    )
    assert summary["reportable_comparison_count"] == 1
    assert summary["coverage_result"] == "HAS_REPORTABLE_COMPARISON"


def test_duplicate_pairs_count_as_one_semantic_unit():
    matches = [
        _match("prop:a", "GROUNDED"),
        _match("prop:a", "CONFLICTS"),  # accidental duplicate; first wins
        _match("prop:b", "UNGROUNDED"),
    ]
    deduped, dropped = distinct_matches_by_law_id(matches)
    assert dropped == 1
    assert [m["law_proposition"]["id"] for m in deduped] == ["prop:a", "prop:b"]
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing={"candidate_count": 2, "classification": "complete"},
        matches=matches,
    )
    assert summary["reportable_comparison_count"] == 1
    assert summary["ungrounded_candidate_count"] == 1


def test_classify_processing_outcomes():
    assert classify_processing(
        candidate_count=0,
        classified_law_ids=set(),
        survivor_law_ids=set(),
        request_succeeded=False,
        parse_succeeded=False,
    ) == ("complete", None)

    assert classify_processing(
        candidate_count=2,
        classified_law_ids=set(),
        survivor_law_ids={"a", "b"},
        request_succeeded=False,
        parse_succeeded=False,
    )[0] == "failed"

    assert classify_processing(
        candidate_count=2,
        classified_law_ids={"a"},
        survivor_law_ids={"a", "b"},
        request_succeeded=True,
        parse_succeeded=True,
    )[0] == "partial"

    assert classify_processing(
        candidate_count=2,
        classified_law_ids={"a", "b"},
        survivor_law_ids={"a", "b"},
        request_succeeded=True,
        parse_succeeded=True,
    ) == ("complete", None)
