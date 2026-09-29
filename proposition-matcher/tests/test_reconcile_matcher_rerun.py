"""Three-way Matcher rerun reconciliation helpers."""

from proposition_matcher.pipeline.reconcile_matcher_rerun import (
    build_reconciliation,
    classify_anna_portability,
    compare_pair_churn,
    recommend_strategy,
)


def _match(law_id: str, relationship: str) -> dict:
    return {
        "law_proposition": {"id": law_id},
        "relationship": relationship,
        "confidence": "high",
        "explanation": "x",
        "correctness_score": 0.5,
    }


def _row(gid: str, matches: list[dict], *, cand: int | None = None) -> dict:
    row = {"id": gid, "matches": matches}
    if cand is not None:
        row["match_processing"] = {"candidate_count": cand, "classification": "complete"}
    return row


def test_changed_top_pairs_and_new_removed():
    historic = [
        _row("g1", [_match("L1", "GROUNDED"), _match("L2", "UNGROUNDED")]),
        _row("g2", [_match("L3", "GUIDANCE_INCOMPLETE")]),
    ]
    new = [
        _row("g1", [_match("L2", "GROUNDED"), _match("L4", "UNGROUNDED")], cand=2),
        _row("g2", [_match("L3", "GUIDANCE_INCOMPLETE")], cand=1),
    ]
    churn = compare_pair_churn(historic, new)
    assert churn["changed_top_pairs"] == 1
    assert churn["new_pairs"] == 1  # g1-L4
    assert churn["removed_pairs"] == 1  # g1-L1
    assert churn["unchanged_distinct_pairs"] == 2  # g1-L2, g2-L3


def test_same_pair_relationship_changed():
    historic = [_row("g1", [_match("L1", "GUIDANCE_INCOMPLETE")])]
    new = [_row("g1", [_match("L1", "GROUNDED")], cand=1)]
    churn = compare_pair_churn(historic, new)
    assert churn["same_pair_relationship_changed"] == 1
    assert churn["same_pair_relationship_changed_samples"][0]["new_relationship"] == "GROUNDED"


def test_missing_historic_pair_portability():
    beatrice = [_row("g1", [_match("L1", "GUIDANCE_INCOMPLETE")])]
    anna = [_row("g1", [_match("L1", "GROUNDED")])]
    new = [_row("g1", [_match("L2", "GROUNDED")], cand=1)]
    port = classify_anna_portability(anna, beatrice, new)
    assert port["portability_counts"]["OLD_PAIR_NOT_PRESENT"] == 1
    assert port["pair_disappeared"][0]["law_proposition_id"] == "L1"


def test_new_pair_and_raw_agrees_with_anna():
    beatrice = [_row("g1", [_match("L1", "GUIDANCE_INCOMPLETE"), _match("L2", "UNGROUNDED")])]
    anna = [_row("g1", [_match("L1", "GROUNDED"), _match("L2", "UNGROUNDED")])]
    new = [_row("g1", [_match("L1", "GROUNDED"), _match("L3", "UNGROUNDED")], cand=2)]
    churn = compare_pair_churn(beatrice, new)
    assert churn["new_pairs"] == 1
    port = classify_anna_portability(anna, beatrice, new)
    assert port["portability_counts"]["UNCHANGED_PAIR_PRESENT"] == 1
    assert port["raw_matcher_already_agrees_with_anna"]


def test_preserves_guidance_broader_in_summary():
    rows = [
        _row(
            "g1",
            [_match("L1", "GUIDANCE_BROADER"), _match("L2", "GROUNDED")],
            cand=2,
        )
    ]
    data = build_reconciliation(
        new_rows=rows,
        beatrice_rows=rows,
        anna_rows=rows,
        acceptance_rows=rows,
        validation={"ready_for_adjudication": True, "ok": True},
    )
    assert data["run_summary"]["new_matcher"]["relationship_distribution"]["GUIDANCE_BROADER"] == 1
    assert "GROUNDED_BROADER" not in data["run_summary"]["new_matcher"]["relationship_distribution"]


def test_distinguishes_raw_matcher_from_adjudicated():
    beatrice = [_row("g1", [_match("L1", "CONFLICTS")])]
    anna = [_row("g1", [_match("L1", "GROUNDED")])]
    new = [_row("g1", [_match("L1", "CONFLICTS")], cand=1)]
    port = classify_anna_portability(anna, beatrice, new)
    assert port["portability_counts"]["PAIR_PRESENT_RELATIONSHIP_DIFFERS"] == 1
    assert not port["raw_matcher_already_agrees_with_anna"]


def test_recommend_pairwise_when_joinable():
    churn = {
        "new_pairs": 5,
        "removed_pairs": 3,
        "changed_top_pairs": 2,
        "same_pair_relationship_changed": 1,
    }
    portability = {
        "historic_adjudications_count": 20,
        "pair_disappeared": [],
        "portability_counts": {
            "UNCHANGED_PAIR_PRESENT": 10,
            "PAIR_PRESENT_RELATIONSHIP_DIFFERS": 8,
            "NEW_TOP_PAIR_DIFFERS": 2,
        },
    }
    strategy, _ = recommend_strategy(
        churn=churn, portability=portability, validation_ready=True
    )
    assert strategy == "PAIRWISE_ADJUDICATION_RECONCILIATION_POSSIBLE"


def test_recommend_full_rerun_on_material_churn():
    churn = {
        "new_pairs": 200,
        "removed_pairs": 180,
        "changed_top_pairs": 40,
        "same_pair_relationship_changed": 50,
    }
    portability = {
        "historic_adjudications_count": 20,
        "pair_disappeared": [{"x": 1}] * 12,
        "portability_counts": {"OLD_PAIR_NOT_PRESENT": 12},
    }
    strategy, _ = recommend_strategy(
        churn=churn, portability=portability, validation_ready=True
    )
    assert strategy == "FULL_ADJUDICATOR_RERUN_REQUIRED"
