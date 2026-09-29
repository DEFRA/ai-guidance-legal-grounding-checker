"""
Regression tests for misclassified territorial application propositions.

Fixture: tests/fixtures/regression/agricultural_land_england_territorial_application.json
"""

from __future__ import annotations

import json

import pytest

from law_proposition_extractor_domain import (
    LegalEffectType,
    Proposition,
    PropositionTier,
    apply_post_extraction_classification,
    apply_proposition_label_enrichment,
    apply_relationship_keys,
    attach_extraction_meta,
    build_relationship_keys,
    classify_extracted_proposition,
    derive_proposition_labels,
    split_proposition_notes,
)
from law_proposition_extractor_domain.territory_normalization import extract_territories_from_text
from tests.fixtures.regression.loader import (
    load_regression_fixture,
    normalize_proposition_from_fixture,
    proposition_record_from_fixture,
)

FIXTURE = load_regression_fixture()
RAW = FIXTURE["raw_extraction"]
EXPECTED = FIXTURE["expected"]


@pytest.fixture
def fixture() -> dict:
    return FIXTURE


def test_fixture_schema_load_compatibility() -> None:
    record = proposition_record_from_fixture(FIXTURE)
    prop = Proposition.model_validate(record)
    assert prop.proposition_text == RAW["proposition_text"]
    assert prop.fragment_locator == RAW["fragment_locator"]
    assert prop.categories == RAW["categories"]
    assert prop.review_notes is None
    assert prop.extraction_debug_meta is not None
    assert prop.extraction_debug_meta.get("display_label") == "Territorial application"
    assert not str(prop.notes).startswith("judit_extraction_meta:")

    roundtrip = json.loads(prop.model_dump_json())
    prop2 = Proposition.model_validate(roundtrip)
    assert prop2.proposition_text == prop.proposition_text
    assert prop2.review_notes is prop.review_notes


def test_fixture_notes_meta_not_human_review() -> None:
    meta = FIXTURE["extraction_meta"]
    notes = attach_extraction_meta("", meta)
    parsed = split_proposition_notes(notes)
    assert parsed.review_notes is None
    assert parsed.extraction_meta == meta

    prop = Proposition.model_validate({**proposition_record_from_fixture(FIXTURE), "notes": notes})
    assert prop.review_notes is None


def test_fixture_classification_helper() -> None:
    result = classify_extracted_proposition(
        proposition_text=RAW["proposition_text"],
        legal_subject=RAW["legal_subject"],
        action=RAW["action"],
        affected_subjects=list(RAW["affected_subjects"]),
        label=RAW["label"],
        categories=list(RAW["categories"]),
        extraction_meta=FIXTURE["extraction_meta"],
    )
    assert result.proposition_tier == PropositionTier(EXPECTED["proposition_tier"])
    assert result.legal_effect_type == LegalEffectType(EXPECTED["legal_effect_type"])
    assert result.territorial_application == EXPECTED["territorial_application"]
    assert any(EXPECTED["affected_subjects_contains"] in s for s in result.affected_subjects)
    assert result.is_compliance_relevant is EXPECTED["is_compliance_relevant"]
    assert result.is_comparison_anchor is EXPECTED["is_comparison_anchor"]


def test_fixture_territory_extraction_helper() -> None:
    places = extract_territories_from_text(RAW["proposition_text"], context="application_scope")
    assert places == EXPECTED["territorial_application"]


def test_fixture_label_generation_helper() -> None:
    prop = Proposition.model_validate(proposition_record_from_fixture(FIXTURE))
    apply_post_extraction_classification(prop)
    bundle = derive_proposition_labels(prop)
    assert bundle.label == EXPECTED["label"]
    assert bundle.short_name == EXPECTED["short_name"]
    assert bundle.slug == EXPECTED["slug"]


def test_fixture_cross_reference_key_generation() -> None:
    prop = normalize_proposition_from_fixture(FIXTURE)
    keys = build_relationship_keys(prop)
    assert prop.label == EXPECTED["label"]
    assert prop.short_name == EXPECTED["short_name"]
    assert prop.slug == EXPECTED["slug"]
    assert prop.proposition_tier == PropositionTier(EXPECTED["proposition_tier"])
    assert prop.legal_effect_type == LegalEffectType(EXPECTED["legal_effect_type"])
    assert prop.territorial_application == EXPECTED["territorial_application"]
    assert prop.is_compliance_relevant is EXPECTED["is_compliance_relevant"]
    assert prop.is_comparison_anchor is EXPECTED["is_comparison_anchor"]
    assert prop.review_notes is EXPECTED["review_notes"]

    prefix = EXPECTED["cross_reference_key_not_prefix"]
    assert prop.cross_reference_key is not None
    assert not prop.cross_reference_key.startswith(prefix)
    assert prop.cross_reference_key == prop.source_scoped_key
    for token in EXPECTED["source_scoped_key_contains"]:
        assert token in (prop.source_scoped_key or "")
    for token in EXPECTED["semantic_comparison_key_contains"]:
        assert token in (prop.semantic_comparison_key or "")
    assert prop.explicit_cross_reference_targets == EXPECTED["explicit_cross_reference_targets"]
    assert keys.explicit_cross_reference_targets == []


def test_fixture_legacy_generic_key_not_retained() -> None:
    prop = normalize_proposition_from_fixture(FIXTURE)
    assert prop.cross_reference_key != RAW["cross_reference_key"]
