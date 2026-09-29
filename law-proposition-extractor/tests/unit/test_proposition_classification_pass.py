from law_proposition_extractor_domain import LegalEffectType, Proposition, PropositionTier
from law_proposition_extractor_pipeline.proposition_classification_pass import apply_post_extraction_classification_pass


def test_classification_pass_mutates_propositions_in_place() -> None:
    props = [
        Proposition(
            id="prop-001",
            topic_id="t",
            source_record_id="s",
            jurisdiction="UK",
            proposition_text="These Regulations apply to agricultural land in England.",
            legal_subject="These Regulations",
            action="apply to",
            affected_subjects=["agricultural land in England"],
        ),
        Proposition(
            id="prop-002",
            topic_id="t",
            source_record_id="s",
            jurisdiction="UK",
            proposition_text="These Regulations may be cited as the Example Regulations.",
            legal_subject="These Regulations",
            action="may be cited as",
        ),
    ]
    out = apply_post_extraction_classification_pass(props)
    assert out is props
    assert props[0].legal_effect_type == LegalEffectType.APPLICATION_SCOPE
    assert props[0].proposition_tier == PropositionTier.SCOPE_RULE
    assert props[1].legal_effect_type == LegalEffectType.CITATION
