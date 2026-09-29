"""Unit tests for the Audit Assembler transform — pure, no IO."""

from audit_assembler.build import build, build_pages
from audit_assembler.law_candidates import merge_law_candidate_locators

CATEGORY = {"id": "slurry", "title": "Slurry", "description": "Slurry management."}

# One audited page, two guidance propositions, two law propositions.
# Proposition Matcher output (results.json shape): reordered, carries its native id, and the
# second prop has no match.
PROPOSITION_MATCHER_OUTPUT = [
    {
        "id": "g-aaa-02",
        "proposition_text": "Do Y.",
        "url": "https://www.gov.uk/a",
        "matches": [
            {
                "law_proposition": {"id": "prop:law1", "proposition_text": "Law one."},
                "relationship": "CONFLICT",  # normalises to CONFLICTS
                "confidence": "high",
                "similarity_score": 0.811234,
                "explanation": "conflicts with law1",
                "correctness_score": 0.0,
            }
        ],
    },
    {
        "id": "g-aaa-01",
        "proposition_text": "Do X.",
        "url": "https://www.gov.uk/a",
        "matches": [],  # zero matches
    },
]

LAW_INPUT = [
    {"id": "prop:law1", "proposition_text": "Law one.", "graph_node": "lex-1"},
    {"id": "prop:law2", "proposition_text": "Law two.", "graph_node": "lex-1"},
]

LEGISLATION_SEED = [
    {"id": 1, "category_id": 1, "name": "Act 1", "url": "https://leg/1",
     "source_record_id": "lex-1"}
]

LEGACY_LAW_PROPS = [
    {"judit_id": "prop:law1", "short_name": "L1", "label": "Law One", "fragment_locator": "s.1"}
]

# Guidance Relevance Filter carries the audited pages (metadata + analytics) and their scores. The
# second page is in the audited corpus but has no guidance, so it is not emitted.
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
    {"url": "https://www.gov.uk/other", "content_id": "cid-o",
     "meta_data": {"scores": {"slurry": 0.1}}},
]

READING_AGE = {"https://www.gov.uk/a": {"word_count": 120, "reading_age": 14}}


def _build():
    return build(
        matcher_output=PROPOSITION_MATCHER_OUTPUT,
        law_input=LAW_INPUT,
        relevance_filter_output=RADIA_OUTPUT,
        legislation_seed=LEGISLATION_SEED,
        legacy_law_props=LEGACY_LAW_PROPS,
        category=CATEGORY,
        reading_age_by_url=READING_AGE,
    )


def test_pages_keyed_by_content_id_with_category_slug():
    files, _ = _build()
    pages = files["pages.json"]
    assert pages == [
        {
            "content_id": "cid-a",
            "category": "slurry",
            "url": "https://www.gov.uk/a",
            "title": "Page A",
            "description": "About A",
            "document_type": "guidance",
        }
    ]


def test_guidance_ids_taken_from_matcher_native_id():
    files, _ = _build()
    ids = {g["id"] for g in files["guidance-propositions.json"]}
    # Both props are emitted as guidance props, keyed by Proposition Matcher's native id.
    assert ids == {"g-aaa-01", "g-aaa-02"}
    assert all(g["content_id"] == "cid-a" for g in files["guidance-propositions.json"])
    for g in files["guidance-propositions.json"]:
        assert "source_paragraphs" in g
        assert "section_locator" in g


def test_guidance_prefers_matcher_content_id_over_url_map():
    """Prop-level content_id wins even when the URL map would differ."""
    proposition_matcher_output = [
        {
            "id": "g-1",
            "url": "https://www.gov.uk/a",
            "content_id": "cid-from-prop",
            "proposition_text": "Do X.",
            "source_paragraphs": ["You must do X."],
            "section_locator": "section:rules",
            "matches": [],
        }
    ]
    files, warnings = build(
        matcher_output=proposition_matcher_output,
        law_input=LAW_INPUT,
        relevance_filter_output=RADIA_OUTPUT,
        legislation_seed=LEGISLATION_SEED,
        legacy_law_props=LEGACY_LAW_PROPS,
        category=CATEGORY,
        reading_age_by_url=READING_AGE,
    )
    gp = files["guidance-propositions.json"][0]
    assert gp["content_id"] == "cid-from-prop"
    assert gp["source_paragraphs"] == ["You must do X."]
    assert gp["section_locator"] == "section:rules"
    assert not any("not in audited pages" in w for w in warnings)


def test_build_pages_keeps_pages_without_content_id():
    warnings = []
    pages = build_pages(
        [{"url": "https://gov.uk/z", "content_id": "", "meta_data": {"title": "Z"}}],
        "slurry",
        warnings,
    )
    assert len(pages) == 1
    assert pages[0]["content_id"] is None
    assert pages[0]["url"] == "https://gov.uk/z"
    assert any("no content_id" in w for w in warnings)


def test_top_match_normalises_conflict_and_links_native_ids():
    files, _ = _build()
    matches = files["proposition-matches.json"]
    top = next(
        m for m in matches
        if m["guidance_proposition_id"] == "g-aaa-02"
    )
    assert top["law_proposition_id"] == "prop:law1"
    assert top["relationship"] == "CONFLICTS"
    assert top["cosine_score"] == 0.8112  # rounded to 4dp
    assert top["id"].startswith("m-")


def test_empty_matches_become_no_match():
    files, _ = _build()
    no_match = [
        m for m in files["proposition-matches.json"] if m["relationship"] == "NO_MATCH"
    ]
    assert len(no_match) == 1
    assert no_match[0]["guidance_proposition_id"] == "g-aaa-01"
    assert no_match[0]["law_proposition_id"] is None
    assert no_match[0]["id"].startswith("m-")
    assert "g-aaa-01" in {g["id"] for g in files["guidance-propositions.json"]}


def test_unmatched_law_prop_becomes_guidance_missing():
    files, _ = _build()
    missing = [
        m for m in files["proposition-matches.json"] if m["relationship"] == "GUIDANCE_MISSING"
    ]
    assert [m["law_proposition_id"] for m in missing] == ["prop:law2"]
    assert missing[0]["guidance_proposition_id"] is None


def test_legislation_rekeyed_by_source_record_id_no_integer_id():
    files, _ = _build()
    assert files["legislation.json"] == [
        {"source_record_id": "lex-1", "category": "slurry", "name": "Act 1", "url": "https://leg/1"}
    ]
    lp = files["legislation-propositions.json"]
    assert {p["id"] for p in lp} == {"prop:law1", "prop:law2"}
    law1 = next(p for p in lp if p["id"] == "prop:law1")
    assert law1["source_record_id"] == "lex-1"
    assert law1["short_name"] == "L1"  # carried from legacy by law-proposition-extractor id
    assert law1["fragment_locator"] == "s.1"
    # Non-legislation.gov.uk instrument URLs cannot be deep-linked.
    assert law1["provision_url"] is None


def test_law_candidates_join_populates_locator_and_provision_url():
    law_input = [
        {"id": "bcand:1", "proposition_text": "Law one.", "graph_node": "lex-1"},
        {"id": "bcand:2", "proposition_text": "Law two.", "graph_node": "lex-1"},
    ]
    candidates = [
        {
            "id": "bcand:1",
            "presentation": {
                "locator_label": "regulation:31:paragraph:6:subparagraph:a"
            },
            "evidence": {
                "fragment_locators": ["regulation:31:paragraph:6:subparagraph:a"]
            },
        },
    ]
    join_warnings: list[str] = []
    joined = merge_law_candidate_locators(law_input, candidates, join_warnings)
    legislation_seed = [
        {
            "id": 1,
            "category_id": 1,
            "name": "Act 1",
            "url": "https://www.legislation.gov.uk/uksi/2015/668/contents/made",
            "source_record_id": "lex-1",
        }
    ]
    files, warnings = build(
        matcher_output=PROPOSITION_MATCHER_OUTPUT,
        law_input=joined,
        relevance_filter_output=RADIA_OUTPUT,
        legislation_seed=legislation_seed,
        legacy_law_props=[],
        category=CATEGORY,
        reading_age_by_url=READING_AGE,
    )
    props = {p["id"]: p for p in files["legislation-propositions.json"]}
    assert props["bcand:1"]["fragment_locator"] == (
        "regulation:31:paragraph:6:subparagraph:a"
    )
    assert props["bcand:1"]["provision_url"] == (
        "https://www.legislation.gov.uk/uksi/2015/668/regulation/31/6"
    )
    assert props["bcand:2"]["fragment_locator"] is None
    assert props["bcand:2"]["provision_url"] == (
        "https://www.legislation.gov.uk/uksi/2015/668"
    )
    assert any("joined fragment_locator" in w for w in join_warnings)
    assert any("no fragment_locator" in w for w in warnings)


def test_relevance_from_relevance_scores_by_content_id():
    files, _ = _build()
    assert files["page-relevance.json"] == [
        {"category": "slurry", "content_id": "cid-a", "relevance_score": 0.73}
    ]


def test_subject_summary_total_pages_is_filter_corpus_size():
    files, _ = _build()
    summary = files["subject-summary.json"][0]
    assert summary["total_pages_audited"] == 2  # len(RADIA_OUTPUT)
    assert summary["pages_relevant"] == 1
    assert summary["laws_found"] == 1
    assert "relevance_threshold" not in summary
    assert summary["proposition_status_counts"]["CONFLICTS"] == 1
    assert summary["proposition_status_counts"]["GUIDANCE_MISSING"] == 1
    assert summary["proposition_status_counts"]["NO_MATCH"] == 1


def test_no_correctness_or_aggregation_files_emitted():
    files, _ = _build()
    assert "page-aggregations.json" not in files
    assert "legislation-aggregations.json" not in files
    # correctness must not leak into any emitted record
    for data in files.values():
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            assert "correctness" not in str(row).lower() or "correctness_score" not in row


def test_analytics_and_reading_age_keyed_by_content_id():
    files, _ = _build()
    assert files["page-analytics.json"] == [
        {
            "content_id": "cid-a",
            "last_updated_date": "2025-01-02",
            "view_count_period": 42,
            "period": "last_12_months",
        }
    ]
    assert files["pages-reading-age.json"] == [
        {"content_id": "cid-a", "url": "https://www.gov.uk/a", "word_count": 120, "reading_age": 14}
    ]


def test_build_pages_falls_back_to_content_api_title_when_corpus_has_none():
    """Empty corpus title -> use the gov.uk content-API title; warn if none anywhere."""
    warnings = []
    records = [
        {"url": "https://gov.uk/a", "content_id": "cid-a",
         "meta_data": {"title": "", "description": "d"}},
        {"url": "https://gov.uk/b", "content_id": "cid-b", "meta_data": {}},
    ]
    pages = build_pages(records, "slurry", warnings, {"https://gov.uk/a": "Fetched Title A"})
    by_url = {p["url"]: p for p in pages}
    assert by_url["https://gov.uk/a"]["title"] == "Fetched Title A"
    assert by_url["https://gov.uk/b"]["title"] == ""
    assert any("no title" in w for w in warnings)


def test_build_pages_prefers_corpus_title_over_content_api():
    pages = build_pages(
        [{"url": "https://gov.uk/a", "content_id": "cid-a",
          "meta_data": {"title": "Corpus Title"}}],
        "slurry", [], {"https://gov.uk/a": "Fetched"},
    )
    assert pages[0]["title"] == "Corpus Title"


def test_legacy_empty_matches_without_processing_is_not_checked():
    """Absence of comparison rows must not become NO_CANDIDATES_FOUND."""
    files, _ = _build()
    summaries = {
        s["guidance_proposition_id"]: s
        for s in files["guidance-proposition-match-summaries.json"]
    }
    assert set(summaries) == {"g-aaa-01", "g-aaa-02"}
    assert summaries["g-aaa-01"]["assessment_status"] == "NOT_CHECKED"
    assert summaries["g-aaa-01"]["coverage_result"] is None
    # Legacy row with matches but no match_processing is also not asserted complete.
    assert summaries["g-aaa-02"]["assessment_status"] == "NOT_CHECKED"


def test_match_summaries_cover_all_assessment_cases():
    matcher_output = [
        {
            "id": "g-reportable",
            "url": "https://www.gov.uk/a",
            "proposition_text": "A",
            "match_processing": {"candidate_count": 1, "classification": "complete"},
            "matches": [{
                "law_proposition": {"id": "prop:law1"},
                "relationship": "GROUNDED",
                "confidence": "high",
                "similarity_score": 0.9,
                "explanation": "ok",
            }],
        },
        {
            "id": "g-multi",
            "url": "https://www.gov.uk/a",
            "proposition_text": "B",
            "match_processing": {"candidate_count": 2, "classification": "complete"},
            "matches": [
                {
                    "law_proposition": {"id": "prop:law1"},
                    "relationship": "GROUNDED",
                    "confidence": "high",
                    "similarity_score": 0.9,
                    "explanation": "ok",
                },
                {
                    "law_proposition": {"id": "prop:law2"},
                    "relationship": "CONFLICTS",
                    "confidence": "high",
                    "similarity_score": 0.8,
                    "explanation": "clash",
                },
            ],
        },
        {
            "id": "g-mixed",
            "url": "https://www.gov.uk/a",
            "proposition_text": "C",
            "match_processing": {"candidate_count": 2, "classification": "complete"},
            "matches": [
                {
                    "law_proposition": {"id": "prop:law1"},
                    "relationship": "GUIDANCE_INCOMPLETE",
                    "confidence": "med",
                    "similarity_score": 0.7,
                    "explanation": "partial",
                },
                {
                    "law_proposition": {"id": "prop:law2"},
                    "relationship": "UNGROUNDED",
                    "confidence": "low",
                    "similarity_score": 0.66,
                    "explanation": "no",
                },
            ],
        },
        {
            "id": "g-ungrounded",
            "url": "https://www.gov.uk/a",
            "proposition_text": "D",
            "match_processing": {"candidate_count": 1, "classification": "complete"},
            "matches": [{
                "law_proposition": {"id": "prop:law2"},
                "relationship": "UNGROUNDED",
                "confidence": "low",
                "similarity_score": 0.7,
                "explanation": "no",
            }],
        },
        {
            "id": "g-empty",
            "url": "https://www.gov.uk/a",
            "proposition_text": "E",
            "match_processing": {"candidate_count": 0, "classification": "complete"},
            "matches": [],
        },
        {
            "id": "g-unchecked",
            "url": "https://www.gov.uk/a",
            "proposition_text": "F",
            "matches": [],
        },
        {
            "id": "g-failed",
            "url": "https://www.gov.uk/a",
            "proposition_text": "G",
            "match_processing": {
                "candidate_count": 2,
                "classification": "failed",
                "failure_reason": "group_rerank_request_failed",
            },
            "matches": [],
        },
        {
            "id": "g-partial",
            "url": "https://www.gov.uk/a",
            "proposition_text": "H",
            "match_processing": {
                "candidate_count": 2,
                "classification": "partial",
                "failure_reason": "not_all_candidates_classified",
            },
            "matches": [{
                "law_proposition": {"id": "prop:law1"},
                "relationship": "UNGROUNDED",
                "confidence": "low",
                "similarity_score": 0.7,
                "explanation": "no",
            }],
        },
    ]
    files, _ = build(
        matcher_output=matcher_output,
        law_input=LAW_INPUT,
        relevance_filter_output=RADIA_OUTPUT,
        legislation_seed=LEGISLATION_SEED,
        legacy_law_props=LEGACY_LAW_PROPS,
        category=CATEGORY,
        reading_age_by_url=READING_AGE,
    )
    summaries = files["guidance-proposition-match-summaries.json"]
    assert [s["guidance_proposition_id"] for s in summaries] == [
        "g-reportable", "g-multi", "g-mixed", "g-ungrounded",
        "g-empty", "g-unchecked", "g-failed", "g-partial",
    ]
    by_id = {s["guidance_proposition_id"]: s for s in summaries}

    assert by_id["g-reportable"]["assessment_status"] == "COMPLETE"
    assert by_id["g-reportable"]["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert by_id["g-reportable"]["reportable_comparison_count"] == 1

    assert by_id["g-multi"]["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert by_id["g-multi"]["reportable_comparison_count"] == 2
    assert len(matcher_output[1]["matches"]) == 2

    assert by_id["g-mixed"]["coverage_result"] == "HAS_REPORTABLE_COMPARISON"
    assert by_id["g-mixed"]["ungrounded_candidate_count"] == 1

    assert by_id["g-ungrounded"]["assessment_status"] == "COMPLETE"
    assert by_id["g-ungrounded"]["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert by_id["g-ungrounded"]["reportable_comparison_count"] == 0
    assert by_id["g-ungrounded"]["ungrounded_candidate_count"] == 1

    assert by_id["g-empty"]["assessment_status"] == "COMPLETE"
    assert by_id["g-empty"]["coverage_result"] == "NO_CANDIDATES_FOUND"
    assert by_id["g-empty"]["candidate_count"] == 0

    assert by_id["g-unchecked"]["assessment_status"] == "NOT_CHECKED"
    assert by_id["g-unchecked"]["coverage_result"] is None

    assert by_id["g-failed"]["assessment_status"] == "FAILED"
    assert by_id["g-failed"]["coverage_result"] is None

    assert by_id["g-partial"]["assessment_status"] == "PARTIAL"
    assert by_id["g-partial"]["coverage_result"] is None

    # Full reportable pairs file agrees with summary counts; UNGROUNDED excluded.
    comps = files["guidance-proposition-law-comparisons.json"]
    assert {c["guidance_proposition_id"] for c in comps} == {
        "g-reportable", "g-multi", "g-mixed",
    }
    assert sum(1 for c in comps if c["guidance_proposition_id"] == "g-multi") == 2
    assert all(c["relationship"] != "UNGROUNDED" for c in comps)

    # Pair-level files still use relationship enum only (no NO_LAW_CANDIDATE).
    for m in files["proposition-matches.json"] + comps:
        assert m["relationship"] != "NO_LAW_CANDIDATE"
        assert m["relationship"] in {
            "GROUNDED", "GUIDANCE_BROADER", "GUIDANCE_INCOMPLETE",
            "CONFLICTS", "UNGROUNDED", "GUIDANCE_MISSING", "NO_MATCH",
        }
