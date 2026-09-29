"""Full reportable guidance–law comparison assembly (not top-match only)."""

from audit_assembler.build import build

CATEGORY = {"id": "slurry", "title": "Slurry", "description": "Slurry management."}

LAW_INPUT = [
    {"id": "prop:law1", "proposition_text": "Law one.", "graph_node": "lex-1"},
    {"id": "prop:law2", "proposition_text": "Law two.", "graph_node": "lex-1"},
    {"id": "prop:law3", "proposition_text": "Law three.", "graph_node": "lex-1"},
]

LEGISLATION_SEED = [
    {"id": 1, "category_id": 1, "name": "Act 1", "url": "https://leg/1",
     "source_record_id": "lex-1"}
]

LEGACY_LAW_PROPS = [
    {"judit_id": "prop:law1", "short_name": "L1", "label": "Law One", "fragment_locator": "s.1"},
]

RADIA_OUTPUT = [
    {
        "url": "https://www.gov.uk/a",
        "content_id": "cid-a",
        "meta_data": {
            "title": "Page A",
            "description": "About A",
            "document_type": "guidance",
            "updated_at": "2025-01-02T10:00:00Z",
            "view_count": 42,
            "scores": {"slurry": 0.73},
        },
    },
]

READING_AGE = {"https://www.gov.uk/a": {"word_count": 120, "reading_age": 14}}


def _pair(law_id: str, relationship: str, score: float = 0.8, explanation: str = "x") -> dict:
    return {
        "law_proposition": {"id": law_id, "proposition_text": f"text {law_id}"},
        "relationship": relationship,
        "confidence": "high",
        "similarity_score": score,
        "explanation": explanation,
    }


def _gp(gp_id: str, matches: list[dict], processing: dict | None = None) -> dict:
    row = {
        "id": gp_id,
        "url": "https://www.gov.uk/a",
        "proposition_text": gp_id,
        "matches": matches,
    }
    if processing is not None:
        row["match_processing"] = processing
    return row


def _build(matcher_output: list[dict]):
    return build(
        matcher_output=matcher_output,
        law_input=LAW_INPUT,
        relevance_filter_output=RADIA_OUTPUT,
        legislation_seed=LEGISLATION_SEED,
        legacy_law_props=LEGACY_LAW_PROPS,
        category=CATEGORY,
        reading_age_by_url=READING_AGE,
    )


def _comparisons(files: dict) -> list[dict]:
    return files["guidance-proposition-law-comparisons.json"]


def _summaries(files: dict) -> dict[str, dict]:
    return {s["guidance_proposition_id"]: s for s in files["guidance-proposition-match-summaries.json"]}


def test_case1_one_reportable_hit():
    files, _ = _build([
        _gp("g-1", [_pair("prop:law1", "GROUNDED", 0.91)],
            {"candidate_count": 1, "classification": "complete"}),
    ])
    comps = _comparisons(files)
    assert len(comps) == 1
    assert comps[0]["guidance_proposition_id"] == "g-1"
    assert comps[0]["law_proposition_id"] == "prop:law1"
    assert comps[0]["relationship"] == "GROUNDED"
    assert comps[0]["cosine_score"] == 0.91
    assert comps[0]["explanation"] == "x"
    assert _summaries(files)["g-1"]["reportable_comparison_count"] == 1
    top = next(
        m for m in files["proposition-matches.json"] if m["guidance_proposition_id"] == "g-1"
    )
    assert top["law_proposition_id"] == "prop:law1"


def test_case2_several_distinct_reportable_hits():
    matches = [
        _pair("prop:law1", "GROUNDED", 0.9, "a"),
        _pair("prop:law2", "CONFLICTS", 0.85, "b"),
        _pair("prop:law3", "GUIDANCE_INCOMPLETE", 0.8, "c"),
    ]
    files, _ = _build([
        _gp("g-multi", matches, {"candidate_count": 3, "classification": "complete"}),
    ])
    comps = _comparisons(files)
    assert [(c["law_proposition_id"], c["relationship"]) for c in comps] == [
        ("prop:law1", "GROUNDED"),
        ("prop:law2", "CONFLICTS"),
        ("prop:law3", "GUIDANCE_INCOMPLETE"),
    ]
    assert _summaries(files)["g-multi"]["reportable_comparison_count"] == 3
    top = next(
        m for m in files["proposition-matches.json"] if m["guidance_proposition_id"] == "g-multi"
    )
    assert top["law_proposition_id"] == "prop:law1"
    assert top["relationship"] == "GROUNDED"


def test_case3_mixed_reportable_and_ungrounded():
    matcher = [
        _gp(
            "g-mixed",
            [
                _pair("prop:law1", "GUIDANCE_BROADER", 0.88),
                _pair("prop:law2", "UNGROUNDED", 0.7),
            ],
            {"candidate_count": 2, "classification": "complete"},
        ),
    ]
    files, _ = _build(matcher)
    comps = _comparisons(files)
    assert len(comps) == 1
    assert comps[0]["law_proposition_id"] == "prop:law1"
    assert comps[0]["relationship"] == "GUIDANCE_BROADER"
    assert all(c["relationship"] != "UNGROUNDED" for c in comps)
    assert len(matcher[0]["matches"]) == 2  # source retains ungrounded
    assert _summaries(files)["g-mixed"]["reportable_comparison_count"] == 1
    assert _summaries(files)["g-mixed"]["ungrounded_candidate_count"] == 1


def test_case4_only_ungrounded():
    files, _ = _build([
        _gp("g-u", [_pair("prop:law1", "UNGROUNDED")],
            {"candidate_count": 1, "classification": "complete"}),
    ])
    assert _comparisons(files) == []
    assert _summaries(files)["g-u"]["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"


def test_case5_no_candidates():
    files, _ = _build([
        _gp("g-empty", [], {"candidate_count": 0, "classification": "complete"}),
    ])
    assert _comparisons(files) == []
    assert _summaries(files)["g-empty"]["coverage_result"] == "NO_CANDIDATES_FOUND"


def test_case6_non_complete_assessments_emit_no_pairs():
    files, warnings = _build([
        _gp("g-unchecked", [_pair("prop:law1", "GROUNDED")]),  # no match_processing
        _gp(
            "g-partial",
            [_pair("prop:law1", "GROUNDED")],
            {"candidate_count": 2, "classification": "partial"},
        ),
        _gp(
            "g-failed",
            [],
            {"candidate_count": 2, "classification": "failed",
             "failure_reason": "group_rerank_request_failed"},
        ),
    ])
    assert _comparisons(files) == []
    by_id = _summaries(files)
    assert by_id["g-unchecked"]["assessment_status"] == "NOT_CHECKED"
    assert by_id["g-partial"]["assessment_status"] == "PARTIAL"
    assert by_id["g-failed"]["assessment_status"] == "FAILED"
    assert not any("count mismatch" in w for w in warnings)


def test_case7_duplicate_pair_deduped_deterministically():
    files, warnings = _build([
        _gp(
            "g-dup",
            [
                _pair("prop:law1", "GROUNDED", 0.9, "first-wins"),
                _pair("prop:law1", "CONFLICTS", 0.95, "duplicate-dropped"),
                _pair("prop:law2", "GUIDANCE_BROADER", 0.8, "other"),
            ],
            {"candidate_count": 2, "classification": "complete"},
        ),
    ])
    comps = _comparisons(files)
    assert [(c["law_proposition_id"], c["relationship"], c["explanation"]) for c in comps] == [
        ("prop:law1", "GROUNDED", "first-wins"),
        ("prop:law2", "GUIDANCE_BROADER", "other"),
    ]
    ids = [c["id"] for c in comps]
    assert len(ids) == len(set(ids))
    assert _summaries(files)["g-dup"]["reportable_comparison_count"] == 2
    assert any("duplicate guidance–law match rows dropped" in w for w in warnings)
    assert not any("count mismatch" in w for w in warnings)


def test_case8_adjudicated_relationship_on_top_pair():
    """Adjudicator mutates matches[0] in place; assembled output reads effective relationship."""
    files, _ = _build([
        _gp(
            "g-adj",
            [
                _pair("prop:law1", "GROUNDED", 0.9, "cleared by adjudicator"),
                _pair("prop:law2", "UNGROUNDED", 0.7, "audit"),
            ],
            {"candidate_count": 2, "classification": "complete"},
        ),
    ])
    comps = _comparisons(files)
    assert len(comps) == 1
    assert comps[0]["relationship"] == "GROUNDED"
    assert comps[0]["explanation"] == "cleared by adjudicator"
    assert _summaries(files)["g-adj"]["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert _summaries(files)["g-adj"]["reportable_comparison_count"] == 1


def test_case8b_adjudicated_clear_makes_only_ungrounded_when_no_other_reportable():
    """If top was the only reportable and stays reportable after adjudicate — still one pair.
    If adjudicator left CONFLICTS as top with a second reportable, both emit."""
    files, _ = _build([
        _gp(
            "g-adj2",
            [
                _pair("prop:law1", "CONFLICTS", 0.9, "still flagged"),
                _pair("prop:law2", "GUIDANCE_INCOMPLETE", 0.85, "also reportable"),
            ],
            {"candidate_count": 2, "classification": "complete"},
        ),
    ])
    comps = _comparisons(files)
    assert len(comps) == 2
    assert comps[0]["relationship"] == "CONFLICTS"
    assert comps[1]["relationship"] == "GUIDANCE_INCOMPLETE"
    # Non-top CONFLICTS/INCOMPLETE are emitted with Matcher relationship; only top may be adjudicated.
    assert _summaries(files)["g-adj2"]["reportable_comparison_count"] == 2


def test_case9_mixed_propositions_counts_agree():
    files, warnings = _build([
        _gp("g-one", [_pair("prop:law1", "GROUNDED")],
            {"candidate_count": 1, "classification": "complete"}),
        _gp(
            "g-multi",
            [
                _pair("prop:law1", "GROUNDED", 0.9),
                _pair("prop:law2", "CONFLICTS", 0.8),
                _pair("prop:law3", "GUIDANCE_BROADER", 0.75),
            ],
            {"candidate_count": 3, "classification": "complete"},
        ),
        _gp("g-ungrounded", [_pair("prop:law2", "UNGROUNDED")],
            {"candidate_count": 1, "classification": "complete"}),
        _gp("g-empty", [], {"candidate_count": 0, "classification": "complete"}),
        _gp(
            "g-failed",
            [],
            {"candidate_count": 2, "classification": "failed",
             "failure_reason": "group_rerank_request_failed"},
        ),
    ])
    by_id = _summaries(files)
    assert set(by_id) == {"g-one", "g-multi", "g-ungrounded", "g-empty", "g-failed"}

    comps = _comparisons(files)
    assert {c["guidance_proposition_id"] for c in comps} == {"g-one", "g-multi"}
    assert sum(1 for c in comps if c["guidance_proposition_id"] == "g-one") == 1
    assert sum(1 for c in comps if c["guidance_proposition_id"] == "g-multi") == 3
    assert by_id["g-one"]["reportable_comparison_count"] == 1
    assert by_id["g-multi"]["reportable_comparison_count"] == 3
    assert by_id["g-ungrounded"]["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert by_id["g-empty"]["coverage_result"] == "NO_CANDIDATES_FOUND"
    assert by_id["g-failed"]["assessment_status"] == "FAILED"
    assert not any("count mismatch" in w for w in warnings)


def test_case10_compatibility_top_match_file_unchanged_shape():
    files, _ = _build([
        _gp(
            "g-1",
            [
                _pair("prop:law1", "CONFLICT", 0.811234, "conflicts"),
                _pair("prop:law2", "GROUNDED", 0.7, "also"),
            ],
            {"candidate_count": 2, "classification": "complete"},
        ),
    ])
    top = next(
        m for m in files["proposition-matches.json"] if m["guidance_proposition_id"] == "g-1"
    )
    assert top["relationship"] == "CONFLICTS"
    assert top["cosine_score"] == 0.8112
    assert top["id"].startswith("m-")
    # Full file still has multi-hit; compatibility file keeps one GP-linked top row.
    assert len(_comparisons(files)) == 2
    gp_linked = [
        m for m in files["proposition-matches.json"] if m["guidance_proposition_id"] == "g-1"
    ]
    assert len(gp_linked) == 1
