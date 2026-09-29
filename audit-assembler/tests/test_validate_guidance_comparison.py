"""Contract validator for assembled guidance–law comparison outputs."""

from pathlib import Path

import pytest

from audit_assembler.validate_guidance_comparison import (
    ContractViolation,
    assert_valid_assembled_dir,
    validate_assembled_payload,
)


def _base_payload(**overrides):
    payload = {
        "guidance_propositions": [
            {"id": "g-1", "proposition_text": "A"},
            {"id": "g-2", "proposition_text": "B"},
        ],
        "legislation_propositions": [
            {"id": "prop:law1"},
            {"id": "prop:law2"},
        ],
        "match_summaries": [
            {
                "guidance_proposition_id": "g-1",
                "assessment_status": "COMPLETE",
                "coverage_result": "HAS_REPORTABLE_COMPARISON",
                "reportable_comparison_count": 2,
                "ungrounded_candidate_count": 0,
                "candidate_count": 2,
            },
            {
                "guidance_proposition_id": "g-2",
                "assessment_status": "COMPLETE",
                "coverage_result": "ONLY_UNGROUNDED_CANDIDATES",
                "reportable_comparison_count": 0,
                "ungrounded_candidate_count": 1,
                "candidate_count": 1,
            },
        ],
        "law_comparisons": [
            {
                "id": "m-1",
                "guidance_proposition_id": "g-1",
                "law_proposition_id": "prop:law1",
                "relationship": "GROUNDED",
            },
            {
                "id": "m-2",
                "guidance_proposition_id": "g-1",
                "law_proposition_id": "prop:law2",
                "relationship": "CONFLICTS",
            },
        ],
        "proposition_matches": [
            {
                "id": "m-top",
                "guidance_proposition_id": "g-1",
                "law_proposition_id": "prop:law1",
                "relationship": "GROUNDED",
            },
            {
                "id": "m-missing",
                "guidance_proposition_id": None,
                "law_proposition_id": "prop:law2",
                "relationship": "GUIDANCE_MISSING",
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_valid_payload_has_no_errors():
    assert validate_assembled_payload(**_base_payload()) == []


def test_summary_count_mismatch():
    payload = _base_payload(
        match_summaries=[
            {
                "guidance_proposition_id": "g-1",
                "assessment_status": "COMPLETE",
                "coverage_result": "HAS_REPORTABLE_COMPARISON",
                "reportable_comparison_count": 2,
            }
        ]
    )
    errors = validate_assembled_payload(**payload)
    assert any("summary completeness" in e for e in errors)
    assert any("g-2" in e for e in errors)


def test_reportable_count_mismatch_names_guidance_id():
    payload = _base_payload()
    payload["match_summaries"][0]["reportable_comparison_count"] = 99
    errors = validate_assembled_payload(**payload)
    assert any(
        "reportable-pair invariant" in e and "g-1" in e and "expected 99" in e and "actual 2" in e
        for e in errors
    )


def test_fallback_must_not_have_pairs():
    payload = _base_payload()
    payload["law_comparisons"].append(
        {
            "id": "m-bad",
            "guidance_proposition_id": "g-2",
            "law_proposition_id": "prop:law1",
            "relationship": "GROUNDED",
        }
    )
    errors = validate_assembled_payload(**payload)
    assert any("no-pair fallback invariant" in e and "g-2" in e for e in errors)


def test_ungrounded_forbidden_in_comparisons():
    payload = _base_payload()
    payload["law_comparisons"].append(
        {
            "id": "m-u",
            "guidance_proposition_id": "g-1",
            "law_proposition_id": "prop:law1",
            "relationship": "UNGROUNDED",
        }
    )
    errors = validate_assembled_payload(**payload)
    assert any("UNGROUNDED" in e and "g-1" in e for e in errors)


def test_duplicate_pairs():
    payload = _base_payload()
    payload["law_comparisons"].append(
        {
            "id": "m-dup",
            "guidance_proposition_id": "g-1",
            "law_proposition_id": "prop:law1",
            "relationship": "GROUNDED",
        }
    )
    errors = validate_assembled_payload(**payload)
    assert any("pair uniqueness" in e and "g-1" in e for e in errors)


def test_assert_valid_raises_contract_violation(tmp_path: Path):
    (tmp_path / "guidance-propositions.json").write_text("[]")
    with pytest.raises(ContractViolation):
        assert_valid_assembled_dir(tmp_path)
