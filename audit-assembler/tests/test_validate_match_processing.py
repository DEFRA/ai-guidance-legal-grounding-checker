"""Assembler boundary: consume approved processing; never invent historic state."""

from __future__ import annotations

import pytest

from audit_assembler.build import build
from audit_assembler.match_summary import summarise_guidance_proposition_match
from audit_assembler.validate_match_processing import validate_matcher_match_processing

CATEGORY = {"id": "demo", "title": "Demo", "description": "d"}
LEGACY_LAW_PROPS: list = []


def _pair(law_id: str, relationship: str = "GROUNDED") -> dict:
    return {
        "law_proposition": {"id": law_id, "proposition_text": "law"},
        "relationship": relationship,
        "confidence": "high",
        "explanation": "x",
        "correctness_score": 0.5,
        "similarity_score": 0.9,
    }


def test_case20_valid_reconstructed_run_accepted():
    matcher = [
        {
            "id": "g-1",
            "url": "https://www.gov.uk/a",
            "proposition_text": "p",
            "matches": [_pair("prop:law1", "UNGROUNDED")],
            "match_processing": {
                "candidate_count": 1,
                "classification": "complete",
                "provenance": {
                    "origin": "historic_backfill",
                    "policy_version": "historic_match_processing_backfill_v1",
                    "evidence_codes": ["SURVIVOR_LIST_PRESENT", "ALL_SURVIVORS_CLASSIFIED"],
                },
            },
        }
    ]
    assert validate_matcher_match_processing(matcher) == []
    files, warnings = build(
        matcher_output=matcher,
        law_input=[{"id": "prop:law1", "proposition_text": "law", "graph_node": "lex-1"}],
        relevance_filter_output=[{
            "url": "https://www.gov.uk/a",
            "content_id": "cid-a",
            "meta_data": {"title": "A", "scores": {"demo": 0.5}},
        }],
        legislation_seed=[{
            "id": 1,
            "category_id": 1,
            "name": "Act",
            "url": "https://leg/1",
            "source_record_id": "lex-1",
        }],
        legacy_law_props=LEGACY_LAW_PROPS,
        category=CATEGORY,
        reading_age_by_url={},
    )
    summaries = files["guidance-proposition-match-summaries.json"]
    assert summaries[0]["assessment_status"] == "COMPLETE"
    assert summaries[0]["coverage_result"] == "ONLY_UNGROUNDED_CANDIDATES"
    assert any("historic_backfill" in w for w in warnings)


def test_case20_legacy_without_processing_not_treated_as_complete():
    summary = summarise_guidance_proposition_match(
        guidance_proposition_id="g-1",
        match_processing=None,
        matches=[],
    )
    assert summary["assessment_status"] == "NOT_CHECKED"
    assert summary["coverage_result"] is None


def test_case20_false_historic_backfill_rejected():
    matcher = [
        {
            "id": "g-1",
            "url": "https://example.test/a",
            "proposition_text": "p",
            "matches": [],
            "match_processing": {
                "candidate_count": 0,
                "classification": "complete",
                "provenance": {
                    "origin": "historic_backfill",
                    "policy_version": "acceptance_only_hack",
                    "evidence_codes": ["FAKE"],
                },
            },
        }
    ]
    errors = validate_matcher_match_processing(matcher)
    assert errors
    with pytest.raises(ValueError, match="historic_backfill"):
        build(
            matcher_output=matcher,
            law_input=[],
            relevance_filter_output=[{
                "url": "https://example.test/a",
                "content_id": "c1",
                "meta_data": {},
            }],
            legislation_seed=[],
            legacy_law_props=LEGACY_LAW_PROPS,
            category=CATEGORY,
            reading_age_by_url={},
        )


def test_acceptance_style_processing_without_provenance_still_allowed():
    """Acceptance-only derived copies lack provenance; Assembler still consumes them."""
    matcher = [
        {
            "id": "g-1",
            "url": "https://example.test/a",
            "proposition_text": "p",
            "matches": [],
            "match_processing": {"candidate_count": 0, "classification": "complete"},
        }
    ]
    assert validate_matcher_match_processing(matcher) == []
