"""Native Matcher run validation gates."""

from proposition_matcher.pipeline.validate_native_run import validate_native_matcher_run


def _row(
    gid: str,
    *,
    candidate_count: int = 1,
    classification: str = "complete",
    matches: list[dict] | None = None,
    failure_reason: str | None = None,
) -> dict:
    mp: dict = {"candidate_count": candidate_count, "classification": classification}
    if failure_reason is not None:
        mp["failure_reason"] = failure_reason
    return {
        "id": gid,
        "match_processing": mp,
        "matches": matches
        if matches is not None
        else (
            []
            if candidate_count == 0
            else [
                {
                    "law_proposition": {"id": "bcand:a"},
                    "relationship": "GROUNDED",
                    "confidence": "high",
                    "explanation": "x",
                    "correctness_score": 0.9,
                }
            ]
        ),
    }


def test_exact_input_result_coverage_ok():
    report = validate_native_matcher_run(
        results=[_row("g1", candidate_count=0, matches=[]), _row("g2")],
        input_guidance_ids=["g1", "g2"],
        survivor_counts={"g1": 0, "g2": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is True
    assert report["ready_for_adjudication"] is True


def test_missing_guidance_result_fails():
    report = validate_native_matcher_run(
        results=[_row("g1")],
        input_guidance_ids=["g1", "g2"],
        survivor_counts={"g1": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is False
    assert any("missing" in e for e in report["errors"])


def test_candidate_count_mismatch():
    report = validate_native_matcher_run(
        results=[_row("g1", candidate_count=2)],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is False
    assert report["candidate_count_mismatches"][0]["recomputed_survivors"] == 1


def test_duplicate_pair_detection():
    matches = [
        {
            "law_proposition": {"id": "bcand:a"},
            "relationship": "GROUNDED",
            "confidence": "high",
            "explanation": "x",
            "correctness_score": 0.9,
        },
        {
            "law_proposition": {"id": "bcand:a"},
            "relationship": "UNGROUNDED",
            "confidence": "low",
            "explanation": "y",
            "correctness_score": 0.1,
        },
    ]
    report = validate_native_matcher_run(
        results=[_row("g1", candidate_count=2, matches=matches)],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 2},
        law_ids={"bcand:a"},
    )
    assert report["duplicate_pairs"] == [
        {"guidance_proposition_id": "g1", "law_proposition_id": "bcand:a"}
    ]


def test_zero_survivors_with_pairs_fails():
    report = validate_native_matcher_run(
        results=[
            _row(
                "g1",
                candidate_count=0,
                matches=[
                    {
                        "law_proposition": {"id": "bcand:a"},
                        "relationship": "GROUNDED",
                        "confidence": "high",
                        "explanation": "x",
                        "correctness_score": 0.9,
                    }
                ],
            )
        ],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 0},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is False
    assert any("zero survivors" in e for e in report["errors"])


def test_failed_classification_not_ready():
    report = validate_native_matcher_run(
        results=[
            _row(
                "g1",
                classification="failed",
                failure_reason="group_rerank_parse_failed",
                matches=[],
            )
        ],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is True  # schema/scope ok
    assert report["ready_for_adjudication"] is False
    assert report["incomplete_guidance_proposition_ids"] == ["g1"]


def test_preserves_guidance_broader_vocabulary():
    matches = [
        {
            "law_proposition": {"id": "bcand:a"},
            "relationship": "GUIDANCE_BROADER",
            "confidence": "high",
            "explanation": "x",
            "correctness_score": 0.8,
        }
    ]
    report = validate_native_matcher_run(
        results=[_row("g1", matches=matches)],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is True
    assert report["unknown_relationships"] == []


def test_rejects_grounded_broader():
    matches = [
        {
            "law_proposition": {"id": "bcand:a"},
            "relationship": "GROUNDED_BROADER",
            "confidence": "high",
            "explanation": "x",
            "correctness_score": 0.8,
        }
    ]
    report = validate_native_matcher_run(
        results=[_row("g1", matches=matches)],
        input_guidance_ids=["g1"],
        survivor_counts={"g1": 1},
        law_ids={"bcand:a"},
    )
    assert report["ok"] is False
    assert report["unknown_relationships"]
