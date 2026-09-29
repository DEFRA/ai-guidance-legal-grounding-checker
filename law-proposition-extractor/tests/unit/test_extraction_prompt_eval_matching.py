"""Prompt-lab evaluator: contained, classification equivalence, and bundled matching."""

from __future__ import annotations

from law_proposition_extractor_pipeline.extraction_prompt_eval import (
    _match_expected_to_actual,
    _score_expected_against_actual,
)


def test_contained_match_finds_expected_condition_inside_actual_conditions() -> None:
    expected = {
        "legal_effect_type": "obligation",
        "proposition_tier": "substantive_rule",
        "proposition_text": "No other organic manure may be spread (Condition 3).",
        "legal_subject": "occupier",
        "action": "must ensure that no other form of organic manure is spread",
        "conditions": ["during the applicable period"],
        "evidence_quote": "Condition 3 is that no other form of organic manure is spread over the land",
    }
    actual = {
        "id": "prop-bundle",
        "legal_effect_type": "permission",
        "proposition_tier": "substantive_rule",
        "proposition_text": "The occupier may exceed the limit if three conditions are met.",
        "legal_subject": "occupier",
        "action": "may exceed the 250kg limit if",
        "conditions": [
            "Condition 3 is that no other form of organic manure is spread over the land in question",
        ],
        "extraction_debug_meta": {
            "evidence_quote": (
                "Condition 3 is that no other form of organic manure is spread over the land in question"
            ),
        },
    }
    _score, detail = _score_expected_against_actual(
        expected,
        actual,
        evaluation_mode="minimum",
    )
    assert detail.matched is True
    assert detail.match_kind in {"contained_in_actual", "bundled_match"}
    assert detail.contained_evidence_ok is True


def test_classification_mismatch_passes_in_minimum_with_equivalent_effects() -> None:
    expected = {
        "legal_effect_type": "permission",
        "proposition_tier": "substantive_rule",
        "proposition_text": "The occupier may apply to the Agency for a derogation.",
        "legal_subject": "the occupier of a holding",
        "action": "may apply to the Agency for a derogation",
        "evidence_quote": "The occupier of a holding may apply to the Agency for a derogation",
    }
    actual = {
        "id": "prop-scope",
        "legal_effect_type": "application_scope",
        "proposition_tier": "scope_rule",
        "proposition_text": "The occupier of a holding may apply to the Agency for a derogation.",
        "legal_subject": "occupier of a holding",
        "action": "may apply to the Agency for a derogation",
        "extraction_debug_meta": {
            "evidence_quote": "The occupier of a holding may apply to the Agency for a derogation",
        },
    }
    _score, detail = _score_expected_against_actual(
        expected,
        actual,
        evaluation_mode="minimum",
    )
    assert detail.matched is True
    assert detail.classification_mismatch is True
    assert detail.match_kind == "classification_mismatch"


def test_classification_mismatch_fails_in_exhaustive_mode() -> None:
    expected = {
        "legal_effect_type": "definition",
        "proposition_tier": "definitional_rule",
        "proposition_text": "'Derogation' means …",
        "legal_subject": "derogation",
        "action": "means",
        "evidence_quote": "Derogation means a derogation granted under this Part",
    }
    actual = {
        "id": "prop-def",
        "legal_effect_type": "derogation",
        "proposition_tier": "substantive_rule",
        "proposition_text": "A derogation means a derogation granted under this Part from the limit.",
        "legal_subject": "derogation",
        "action": "means",
        "extraction_debug_meta": {
            "evidence_quote": "Derogation means a derogation granted under this Part from the limit",
        },
    }
    _score, detail = _score_expected_against_actual(
        expected,
        actual,
        evaluation_mode="exhaustive",
    )
    assert detail.matched is False
    assert "classification mismatch" in (detail.suggested_failure_reason or "")


def test_bundled_match_in_minimum_allows_multiple_expected_on_one_actual() -> None:
    actual = {
        "id": "prop-grass",
        "legal_effect_type": "derogation",
        "proposition_tier": "substantive_rule",
        "proposition_text": "Regulation 8 does not apply if grassland requirements are met.",
        "legal_subject": "regulation 8",
        "action": "does not apply if",
        "conditions": [
            "at least 80% of the holding's agricultural area is sown with grass",
            "100kg organic manure nitrogen per hectare",
        ],
        "extraction_debug_meta": {
            "evidence_quote": "at least 80% of the holding's agricultural area is sown with grass",
        },
    }
    expected_a = {
        "legal_effect_type": "derogation",
        "proposition_tier": "substantive_rule",
        "proposition_text": "Regulation 8 does not apply when grassland requirements met.",
        "legal_subject": "regulation 8",
        "action": "does not apply if",
        "evidence_quote": "Regulation 8 does not apply if grassland requirements are met",
    }
    expected_b = {
        "legal_effect_type": "prohibition",
        "proposition_tier": "substantive_rule",
        "proposition_text": "80% grass requirement.",
        "legal_subject": "occupier",
        "action": "must meet throughout the year",
        "conditions": ["at least 80% of the holding's agricultural area is sown with grass"],
        "evidence_quote": "at least 80% of the holding's agricultural area is sown with grass",
    }
    matches = _match_expected_to_actual(
        [expected_a, expected_b],
        [actual],
        evaluation_mode="minimum",
    )
    assert all(m.matched for m in matches)
    assert matches[0].match_kind == "exact"
    assert matches[1].match_kind in {"bundled_match", "contained_in_actual", "classification_mismatch"}
