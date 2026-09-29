"""Legacy categories must not drive compliance-only or canonical classification."""

from __future__ import annotations

from law_proposition_extractor_domain import LegalEffectType, Proposition, PropositionTier, classify_extracted_proposition
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import (
    compliance_relevant_only_visible,
    explorer_visible_default,
)


def test_classify_ignores_legacy_obligation_category_on_application_scope() -> None:
    result = classify_extracted_proposition(
        proposition_text="These Regulations apply to agricultural land in England.",
        legal_subject="These Regulations",
        action="apply to",
        categories=["obligation"],
    )
    assert result.legal_effect_type is LegalEffectType.APPLICATION_SCOPE
    assert result.is_compliance_relevant is False
    assert result.is_comparison_anchor is True


def test_compliance_only_excludes_legacy_obligation_category_mismatch() -> None:
    prop = Proposition(
        id="prop-legacy-cat-scope",
        topic_id="topic-001",
        source_record_id="src-001",
        jurisdiction="UK",
        proposition_text="These Regulations apply to agricultural land in England.",
        legal_subject="These Regulations",
        action="apply to",
        categories=["obligation"],
        proposition_tier=PropositionTier.SCOPE_RULE,
        legal_effect_type=LegalEffectType.APPLICATION_SCOPE,
        is_compliance_relevant=False,
        is_comparison_anchor=True,
    )
    assert "obligation" in prop.categories
    assert explorer_visible_default(prop) is True
    assert compliance_relevant_only_visible(prop) is False
