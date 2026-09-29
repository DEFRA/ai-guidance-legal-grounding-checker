from law_proposition_extractor_domain import (
    LegalEffectType,
    Proposition,
    PropositionTier,
    apply_post_extraction_classification,
    apply_proposition_jurisdiction_fields,
    build_instrument_extent_by_source,
    classify_extracted_proposition,
)
from law_proposition_extractor_pipeline.proposition_jurisdiction_pass import apply_post_extraction_jurisdiction_pass


def test_application_scope_england_with_instrument_extent() -> None:
    extent_prop = Proposition(
        id="prop-extent",
        topic_id="t",
        source_record_id="src-uk",
        jurisdiction="UK",
        proposition_text="These Regulations extend to England and Wales.",
        legal_subject="These Regulations",
        action="extend to",
    )
    apply_post_extraction_classification(extent_prop)

    scope_prop = Proposition(
        id="prop-scope",
        topic_id="t",
        source_record_id="src-uk",
        jurisdiction="UK",
        proposition_text="These Regulations apply to agricultural land in England.",
        legal_subject="These Regulations",
        action="apply to",
        affected_subjects=["agricultural land in England"],
    )
    apply_post_extraction_classification(scope_prop)

    apply_post_extraction_jurisdiction_pass([extent_prop, scope_prop])

    assert extent_prop.legal_effect_type == LegalEffectType.EXTENT
    assert extent_prop.extent == ["England", "Wales"]
    assert scope_prop.legal_effect_type == LegalEffectType.APPLICATION_SCOPE
    assert scope_prop.territorial_application == ["England"]
    assert scope_prop.source_jurisdiction == "UK"
    assert scope_prop.jurisdiction == "UK"
    assert scope_prop.extent == ["England", "Wales"]
    assert any("agricultural land" in s for s in scope_prop.affected_subjects)


def test_classify_extracted_proposition_territory_fields() -> None:
    result = classify_extracted_proposition(
        proposition_text="These Regulations apply to agricultural land in England.",
        legal_subject="These Regulations",
        action="apply to",
        affected_subjects=["agricultural land in England"],
    )
    assert result.proposition_tier == PropositionTier.SCOPE_RULE
    assert result.territorial_application == ["England"]


def test_build_instrument_extent_by_source() -> None:
    props = [
        Proposition(
            id="p1",
            topic_id="t",
            source_record_id="s1",
            jurisdiction="UK",
            proposition_text="These Regulations extend to Scotland only.",
            legal_subject="These Regulations",
            action="extend to",
            legal_effect_type=LegalEffectType.EXTENT,
            extent=["Scotland"],
        )
    ]
    assert build_instrument_extent_by_source(props) == {"s1": ["Scotland"]}


def test_legacy_proposition_without_source_jurisdiction_field() -> None:
    prop = Proposition.model_validate(
        {
            "id": "prop-legacy",
            "topic_id": "t",
            "source_record_id": "s",
            "jurisdiction": "UK",
            "proposition_text": "A person must comply.",
            "legal_subject": "A person",
            "action": "comply",
        }
    )
    assert prop.source_jurisdiction == "UK"
    assert prop.jurisdiction == "UK"
