"""Deterministic proposition label / short_name / slug generation."""

from law_proposition_extractor_domain import (
    LegalEffectType,
    Proposition,
    apply_post_extraction_classification,
    apply_proposition_label_enrichment,
    derive_proposition_labels,
    is_generic_display_label,
    should_preserve_existing_label,
)


def _classified(**kwargs: object) -> Proposition:
    prop = Proposition.model_validate(
        {
            "id": "prop-test",
            "topic_id": "t",
            "source_record_id": "s",
            "jurisdiction": "UK",
            "proposition_text": "",
            "legal_subject": "These Regulations",
            "action": "",
            **kwargs,
        }
    )
    apply_post_extraction_classification(prop)
    return prop


def test_application_scope_agricultural_land_england() -> None:
    prop = _classified(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        affected_subjects=["agricultural land in England"],
        label="Territorial application",
    )
    bundle = derive_proposition_labels(prop)
    assert bundle.label == "Application to agricultural land in England"
    assert bundle.short_name == "Agricultural land in England"
    assert bundle.slug == "application-agricultural-land-in-england"
    assert prop.legal_effect_type == LegalEffectType.APPLICATION_SCOPE


def test_extent_england_and_wales() -> None:
    prop = _classified(
        proposition_text="These Regulations extend to England and Wales.",
        action="extend to",
        label="Territorial extent",
    )
    bundle = derive_proposition_labels(prop)
    assert bundle.label == "Extent to England and Wales"
    assert bundle.short_name == "England and Wales extent"
    assert bundle.slug == "extent-england-and-wales"


def test_commencement_2_april_2018() -> None:
    prop = _classified(
        proposition_text="These Regulations come into force on 2nd April 2018.",
        action="come into force on",
        label="Commencement date",
    )
    bundle = derive_proposition_labels(prop)
    assert bundle.label == "Commencement on 2 April 2018"
    assert bundle.short_name == "Commencement: 2 April 2018"
    assert bundle.slug == "commencement-2018-04-02"


def test_citation_diffuse_pollution_regulations() -> None:
    title = (
        "Reduction and Prevention of Agricultural Diffuse Pollution (England) Regulations 2018"
    )
    prop = _classified(
        proposition_text=f"These Regulations may be cited as the {title}.",
        action="may be cited as",
        label="Citation",
    )
    bundle = derive_proposition_labels(prop)
    assert bundle.label == f"Citation as {title}"
    assert bundle.short_name == "Citation"
    assert bundle.slug.startswith("citation-reduction-and-prevention-of-agricultural")


def test_regulation_1_boilerplate_outputs() -> None:
    cases = [
        (
            "These Regulations may be cited as the Example (England) Regulations 2018.",
            "may be cited as",
            "Citation",
            "Citation as Example (England) Regulations 2018",
        ),
        (
            "These Regulations come into force on 6th April 2010.",
            "come into force on",
            "Commencement date",
            "Commencement on 6 April 2010",
        ),
        (
            "These Regulations extend to England and Wales.",
            "extend to",
            "Territorial extent",
            "Extent to England and Wales",
        ),
        (
            "These Regulations apply to agricultural land in England.",
            "apply to",
            "Territorial application",
            "Application to agricultural land in England",
        ),
    ]
    labels: list[str] = []
    for text, action, display_label, expected_label in cases:
        prop = _classified(
            proposition_text=text,
            action=action,
            label=display_label,
            fragment_locator="regulation:1",
        )
        apply_proposition_label_enrichment(prop)
        assert prop.label == expected_label
        labels.append(prop.label)
    assert len(set(labels)) == 4


def test_preserves_specific_manual_label() -> None:
    prop = _classified(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        label="Custom reviewer label for reg 2(3)",
    )
    apply_proposition_label_enrichment(prop)
    assert prop.label == "Custom reviewer label for reg 2(3)"
    assert should_preserve_existing_label("Custom reviewer label for reg 2(3)")
    assert is_generic_display_label("Territorial application")
    assert not should_preserve_existing_label("Territorial application")


def test_display_label_stored_in_extraction_meta() -> None:
    prop = _classified(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        label="Territorial application",
    )
    apply_proposition_label_enrichment(prop)
    assert prop.extraction_debug_meta is not None
    assert prop.extraction_debug_meta.get("display_label") == "Territorial application"
