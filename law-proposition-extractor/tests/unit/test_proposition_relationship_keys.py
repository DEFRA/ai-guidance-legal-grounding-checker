"""Safer proposition relationship / cross-reference key generation."""

from law_proposition_extractor_domain import (
    LegalEffectType,
    Proposition,
    apply_post_extraction_classification,
    apply_relationship_keys,
    build_relationship_keys,
    is_placeholder_subject,
    should_auto_link_propositions,
)


def _prop(
    *,
    source_record_id: str = "src-slurry-2010",
    proposition_text: str,
    legal_subject: str = "These Regulations",
    action: str = "",
    affected_subjects: list[str] | None = None,
    proposition_id: str = "prop-001",
) -> Proposition:
    p = Proposition(
        id=proposition_id,
        topic_id="t",
        source_record_id=source_record_id,
        jurisdiction="UK",
        proposition_text=proposition_text,
        legal_subject=legal_subject,
        action=action,
        affected_subjects=affected_subjects or [],
    )
    apply_post_extraction_classification(p)
    apply_relationship_keys(p)
    return p


def test_placeholder_subject_detection() -> None:
    assert is_placeholder_subject("These Regulations")
    assert is_placeholder_subject("this Regulation")
    assert not is_placeholder_subject("An occupier")


def test_application_scope_agricultural_land_england_keys() -> None:
    prop = _prop(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        affected_subjects=["agricultural land in England"],
    )
    keys = build_relationship_keys(prop)
    assert keys.source_scoped_key.startswith("lex-")
    assert "application_scope" in keys.source_scoped_key
    assert "england" in keys.source_scoped_key
    assert "agricultural" in keys.source_scoped_key
    assert keys.semantic_comparison_key == keys.source_scoped_key.split(":", 1)[1]
    assert "application_scope" in keys.semantic_comparison_key
    assert "england" in keys.semantic_comparison_key
    assert keys.explicit_cross_reference_targets == []
    assert prop.cross_reference_key == prop.source_scoped_key


def test_unrelated_instruments_same_apply_to_text_not_linked() -> None:
    text = "These Regulations apply to agricultural land in England."
    a = _prop(source_record_id="src-instrument-a", proposition_text=text, action="apply to", proposition_id="pa")
    b = _prop(source_record_id="src-instrument-b", proposition_text=text, action="apply to", proposition_id="pb")

    assert a.source_scoped_key != b.source_scoped_key
    assert a.semantic_comparison_key == b.semantic_comparison_key
    assert not should_auto_link_propositions(a, b)
    assert a.cross_reference_targets == []
    assert b.cross_reference_targets == []


def test_same_source_duplicate_extractions_may_link() -> None:
    text = "These Regulations apply to agricultural land in England."
    a = _prop(source_record_id="src-same", proposition_text=text, action="apply to", proposition_id="pa")
    b = _prop(source_record_id="src-same", proposition_text=text, action="apply to", proposition_id="pb")
    assert a.source_scoped_key == b.source_scoped_key
    assert should_auto_link_propositions(a, b)


def test_legacy_generic_cross_reference_key_not_used() -> None:
    prop = _prop(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
    )
    assert prop.cross_reference_key is not None
    assert not prop.cross_reference_key.startswith("uk:these-regulations")


def test_citation_and_commencement_have_no_semantic_comparison_key() -> None:
    cite = _prop(
        proposition_text="These Regulations may be cited as the Example Regulations 2018.",
        action="may be cited as",
    )
    comm = _prop(
        proposition_text="These Regulations come into force on 2nd April 2018.",
        action="come into force on",
    )
    assert cite.semantic_comparison_key in (None, "")
    assert comm.semantic_comparison_key in (None, "")
    assert "citation" in cite.source_scoped_key
    assert "commencement" in comm.source_scoped_key


def test_extent_keys_include_territories() -> None:
    prop = _prop(
        proposition_text="These Regulations extend to England and Wales.",
        action="extend to",
    )
    keys = build_relationship_keys(prop)
    assert "extent" in keys.source_scoped_key
    assert "england" in keys.source_scoped_key
    assert "wales" in keys.source_scoped_key


def test_explicit_cross_reference_targets_from_text() -> None:
    prop = _prop(
        proposition_text="The occupier must comply with regulation 5 pursuant to Article 10.",
        legal_subject="occupier",
        action="comply with regulation 5",
    )
    assert "regulation 5" in prop.explicit_cross_reference_targets
    assert "article 10" in prop.explicit_cross_reference_targets


def test_obligation_uses_meaningful_subject_not_placeholder() -> None:
    prop = _prop(
        proposition_text="An occupier must not spread slurry within 10 metres of water.",
        legal_subject="occupier",
        action="not spread slurry within 10 metres of water",
    )
    keys = build_relationship_keys(prop)
    assert "these_regulations" not in keys.source_scoped_key
    assert "occupier" in keys.semantic_comparison_key
