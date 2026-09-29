"""Quality gates for post-extraction proposition normalisation."""

from __future__ import annotations

import json

import pytest

from law_proposition_extractor_domain import LegalEffectType, Proposition, PropositionTier, apply_post_extraction_classification
from law_proposition_extractor_pipeline.proposition_quality_gates import (
    check_proposition,
    run_proposition_quality_gates,
    write_normalisation_quality_artifacts,
)
from tests.fixtures.regression.loader import (
    load_regression_fixture,
    normalize_proposition_from_fixture,
    proposition_record_from_fixture,
)

FIXTURE = load_regression_fixture()


def _finding_ids(prop: Proposition, *, newly_normalised: bool = True) -> set[str]:
    return {f.check_id for f in check_proposition(prop, newly_normalised=newly_normalised)}


def test_territorial_fixture_clean_after_normalisation() -> None:
    prop = normalize_proposition_from_fixture()
    report = run_proposition_quality_gates([prop], newly_normalised=True)
    assert report.error_count == 0
    assert "dangerous_legacy_relationship_key" not in _finding_ids(prop)
    assert "debug_leakage" not in _finding_ids(prop)
    assert "scope_application_conflict" not in _finding_ids(prop)
    assert "generic_label_still_present" not in _finding_ids(prop)
    assert "missing_source_scoped_key" not in _finding_ids(prop)
    assert prop.source_scoped_key
    assert prop.territorial_application == FIXTURE["expected"]["territorial_application"]


def test_territorial_fixture_legacy_category_warning_only() -> None:
    prop = normalize_proposition_from_fixture()
    ids = _finding_ids(prop)
    assert "legacy_category_conflict" in ids
    assert prop.is_compliance_relevant is False
    assert "obligation" in prop.categories


def test_raw_fixture_triggers_legacy_key_error() -> None:
    prop = Proposition.model_validate(proposition_record_from_fixture())
    apply_post_extraction_classification(prop)
    findings = check_proposition(prop, newly_normalised=True)
    key_findings = [f for f in findings if f.check_id == "dangerous_legacy_relationship_key"]
    assert key_findings
    assert key_findings[0].severity == "error"
    assert prop.cross_reference_key == FIXTURE["raw_extraction"]["cross_reference_key"]


def test_raw_fixture_generic_label_warning() -> None:
    prop = Proposition.model_validate(proposition_record_from_fixture())
    findings = check_proposition(prop, newly_normalised=False)
    assert any(f.check_id == "generic_label_still_present" for f in findings)


def test_scope_application_conflict_when_territory_missing() -> None:
    prop = normalize_proposition_from_fixture()
    prop.territorial_application = []
    assert "scope_application_conflict" in _finding_ids(prop)


def test_scope_application_no_conflict_for_subject_scope() -> None:
    prop = Proposition.model_validate(
        {
            "id": "prop-subject-scope",
            "topic_id": "topic-test",
            "source_record_id": "lex-1",
            "fragment_locator": "regulation 9",
            "jurisdiction": "UK",
            "legal_subject": "Regulation 9",
            "action": "applies to",
            "proposition_text": (
                "Regulation 9 applies to any silo, slurry or fuel oil storage system "
                "whose construction is to be begun on or after 1 March 1991."
            ),
            "label": "Application to storage systems",
            "proposition_tier": "scope_rule",
            "legal_effect_type": "application_scope",
            "territorial_application": [],
        }
    )
    assert "scope_application_conflict" not in _finding_ids(prop)


def test_scope_application_no_conflict_for_conditional_scope() -> None:
    prop = Proposition.model_validate(
        {
            "id": "prop-conditional-scope",
            "topic_id": "topic-test",
            "source_record_id": "lex-1",
            "fragment_locator": "regulation 24",
            "jurisdiction": "UK",
            "legal_subject": "Regulations 24(1) and 25(1)",
            "action": "do not apply to",
            "proposition_text": (
                "Regulations 24(1) and 25(1) do not apply to a silo or slurry storage system "
                "where construction, substantial reconstruction or substantial enlargement "
                "was begun before 1 March 1991."
            ),
            "label": "Exemption for pre-1991 systems",
            "proposition_tier": "scope_rule",
            "legal_effect_type": "application_scope",
            "territorial_application": [],
        }
    )
    assert "scope_application_conflict" not in _finding_ids(prop)


def test_scope_application_conflict_for_territorial_apply_in() -> None:
    prop = Proposition.model_construct(
        id="prop-territorial-in",
        topic_id="topic-test",
        source_record_id="lex-1",
        fragment_locator="regulation 1",
        jurisdiction="UK",
        legal_subject="This regulation",
        action="applies in",
        proposition_text="This regulation applies in Scotland.",
        label="Application in Scotland",
        proposition_tier=PropositionTier.SCOPE_RULE,
        legal_effect_type=LegalEffectType.APPLICATION_SCOPE,
        territorial_application=[],
    )
    assert "scope_application_conflict" in _finding_ids(prop)


def test_agricultural_land_england_no_conflict_when_territory_present() -> None:
    prop = normalize_proposition_from_fixture()
    assert prop.territorial_application == ["England"]
    assert "scope_application_conflict" not in _finding_ids(prop)


def test_debug_leakage_in_review_notes() -> None:
    prop = normalize_proposition_from_fixture()
    prop.review_notes = "judit_extraction_meta:{\"leaked\": true}"
    findings = check_proposition(prop)
    assert any(f.check_id == "debug_leakage" and f.severity == "error" for f in findings)


def test_comparison_anchor_mismatch_on_citation() -> None:
    prop = normalize_proposition_from_fixture()
    prop.legal_effect_type = LegalEffectType.CITATION
    prop.is_comparison_anchor = True
    assert "comparison_anchor_mismatch" in _finding_ids(prop)


def test_write_artifacts_roundtrip(tmp_path) -> None:
    prop = normalize_proposition_from_fixture()
    report = run_proposition_quality_gates([prop], newly_normalised=True)
    md_path, json_path = write_normalisation_quality_artifacts(tmp_path, report)
    assert md_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["proposition_count"] == 1
    assert "findings" in payload
    assert "Proposition normalisation quality" in md_path.read_text(encoding="utf-8")
