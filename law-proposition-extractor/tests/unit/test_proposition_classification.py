import json

import pytest

from law_proposition_extractor_domain import (
    LegalEffectType,
    Proposition,
    PropositionTier,
    apply_post_extraction_classification,
    classify_extracted_proposition,
)
from law_proposition_extractor_domain.proposition_classification import (
    application_scope_requires_territory,
    classify_application_scope_kind,
    derive_is_comparison_anchor,
    derive_is_compliance_relevant,
    derive_legal_effect_type,
)


def _classify(**kwargs: object):
    return classify_extracted_proposition(**kwargs)  # type: ignore[arg-type]


def test_legacy_proposition_json_loads_without_classification_fields() -> None:
    legacy = {
        "id": "prop-legacy-001",
        "topic_id": "topic-001",
        "source_record_id": "src-001",
        "jurisdiction": "UK",
        "proposition_text": "Operators must keep records.",
        "legal_subject": "operator",
        "action": "keep records",
    }
    prop = Proposition.model_validate(legacy)
    assert prop.proposition_tier == PropositionTier.SUBSTANTIVE_RULE
    assert prop.legal_effect_type == LegalEffectType.RECORDKEEPING
    assert prop.is_compliance_relevant is True
    assert prop.is_comparison_anchor is True


def test_citation() -> None:
    r = _classify(
        proposition_text="These Regulations may be cited as the Example Regulations 2026.",
        legal_subject="These Regulations",
        action="may be cited as",
        label="Citation",
    )
    assert r.proposition_tier == PropositionTier.INSTRUMENT_METADATA
    assert r.legal_effect_type == LegalEffectType.CITATION
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is False


def test_citation_overrides_wrong_provision_type_from_extraction_meta() -> None:
    r = _classify(
        proposition_text=(
            "These Regulations may be cited as the Reduction and Prevention of "
            "Agricultural Diffuse Pollution (England) Regulations 2018."
        ),
        legal_subject="These Regulations",
        action="may be cited as",
        label="Citation",
        extraction_meta={"provision_type": "definition"},
        categories=["obligation"],
    )
    assert r.legal_effect_type == LegalEffectType.CITATION
    assert r.proposition_tier == PropositionTier.INSTRUMENT_METADATA


def test_commencement() -> None:
    r = _classify(
        proposition_text="These Regulations come into force on 1 May 2026.",
        legal_subject="These Regulations",
        action="come into force on",
        label="Commencement",
    )
    assert r.proposition_tier == PropositionTier.INSTRUMENT_METADATA
    assert r.legal_effect_type == LegalEffectType.COMMENCEMENT
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is False


def test_extent_england_and_wales() -> None:
    r = _classify(
        proposition_text="These Regulations extend to England and Wales.",
        legal_subject="These Regulations",
        action="extend to",
    )
    assert r.proposition_tier == PropositionTier.INSTRUMENT_METADATA
    assert r.legal_effect_type == LegalEffectType.EXTENT
    assert "England" in r.extent
    assert "Wales" in r.extent
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is False


def test_application_scope_territorial_and_subject() -> None:
    r = _classify(
        proposition_text="These Regulations apply to agricultural land in England.",
        legal_subject="These Regulations",
        action="apply to",
        affected_subjects=["agricultural land in England"],
        label="Territorial application",
    )
    assert r.proposition_tier == PropositionTier.SCOPE_RULE
    assert r.legal_effect_type == LegalEffectType.APPLICATION_SCOPE
    assert "England" in r.territorial_application
    assert any("agricultural land" in s for s in r.affected_subjects)
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is True
    assert classify_application_scope_kind(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        affected_subjects=["agricultural land in England"],
    ) == "territorial"
    assert application_scope_requires_territory(
        proposition_text="These Regulations apply to agricultural land in England.",
        action="apply to",
        affected_subjects=["agricultural land in England"],
    )


def test_application_scope_kind_subject_object() -> None:
    assert (
        classify_application_scope_kind(
            proposition_text=(
                "Regulation 9 applies to any silo, slurry or fuel oil storage system "
                "whose construction is to be begun on or after 1 March 1991."
            ),
            action="applies to",
        )
        == "subject_object"
    )
    assert not application_scope_requires_territory(
        proposition_text=(
            "Regulation 9 applies to any silo, slurry or fuel oil storage system "
            "whose construction is to be begun on or after 1 March 1991."
        ),
        action="applies to",
    )


def test_application_scope_kind_conditional() -> None:
    assert (
        classify_application_scope_kind(
            proposition_text=(
                "Where the occupier of a qualifying grassland holding intends to apply "
                "nitrogen in grazing livestock manure, enhanced nutrient management "
                "requirements apply."
            ),
        )
        == "conditional"
    )


def test_application_scope_kind_territorial_apply_in() -> None:
    assert (
        classify_application_scope_kind(
            proposition_text="These Regulations apply in England.",
            action="apply in",
        )
        == "territorial"
    )


def test_definition_quoted_means() -> None:
    r = _classify(
        proposition_text="'slurry' means excreta produced by livestock.",
        legal_subject="slurry",
        action="means",
        extraction_meta={"provision_type": "definition"},
        label="Definition of slurry",
    )
    assert r.proposition_tier == PropositionTier.DEFINITIONAL_RULE
    assert r.legal_effect_type == LegalEffectType.DEFINITION
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is True


def test_obligation_person_must() -> None:
    r = _classify(
        proposition_text="A person must keep a movement register before dispatch.",
        legal_subject="A person",
        action="keep a movement register before dispatch",
    )
    assert r.proposition_tier == PropositionTier.SUBSTANTIVE_RULE
    assert r.legal_effect_type == LegalEffectType.OBLIGATION
    assert r.is_compliance_relevant is True
    assert r.is_comparison_anchor is True


def test_prohibition_occupier_must_not() -> None:
    r = _classify(
        proposition_text="An occupier must not spread slurry within 10 metres of water.",
        legal_subject="occupier",
        action="not spread slurry within 10 metres of water",
    )
    assert r.legal_effect_type == LegalEffectType.PROHIBITION
    assert r.is_compliance_relevant is True


def test_notification_procedural() -> None:
    r = _classify(
        proposition_text="The operator must notify the Agency within 14 days.",
        legal_subject="operator",
        action="notify the Agency within 14 days",
    )
    assert r.legal_effect_type == LegalEffectType.NOTIFICATION
    assert r.proposition_tier == PropositionTier.PROCEDURAL_RULE
    assert r.is_compliance_relevant is True


def test_recordkeeping() -> None:
    r = _classify(
        proposition_text="The occupier must make a record of livestock numbers.",
        legal_subject="occupier",
        action="make a record of livestock numbers",
    )
    assert r.legal_effect_type == LegalEffectType.RECORDKEEPING
    assert r.is_compliance_relevant is True


def test_enforcement_offence() -> None:
    r = _classify(
        proposition_text="A person who contravenes this regulation commits an offence.",
        legal_subject="A person",
        action="who contravenes this regulation commits an offence",
    )
    assert r.legal_effect_type == LegalEffectType.ENFORCEMENT
    assert r.proposition_tier == PropositionTier.PROCEDURAL_RULE
    assert r.is_compliance_relevant is True


def test_unknown_empty_text() -> None:
    r = _classify(proposition_text="", legal_subject="", action="")
    assert r.proposition_tier == PropositionTier.UNKNOWN
    assert r.legal_effect_type == LegalEffectType.UNKNOWN
    assert r.is_compliance_relevant is False
    assert r.is_comparison_anchor is False


def test_provision_type_meta_definition() -> None:
    effect = derive_legal_effect_type(
        proposition_text="Slurry means excreta from livestock.",
        legal_subject="slurry",
        action="means",
        extraction_meta={"provision_type": "definition"},
    )
    assert effect is LegalEffectType.DEFINITION


def test_post_extraction_classification_on_proposition_model() -> None:
    prop = Proposition(
        id="prop-001",
        topic_id="topic-001",
        source_record_id="src-001",
        jurisdiction="UK",
        proposition_text="These Regulations may be cited as the Nitrate Regulations 2015.",
        legal_subject="These Regulations",
        action="may be cited as",
        extraction_debug_meta={"extraction_mode": "frontier", "provision_type": "core"},
    )
    apply_post_extraction_classification(prop)
    assert prop.legal_effect_type == LegalEffectType.CITATION
    assert prop.is_comparison_anchor is False


def test_export_round_trip_includes_classification_fields() -> None:
    prop = Proposition(
        id="prop-001",
        topic_id="topic-001",
        source_record_id="src-001",
        jurisdiction="UK",
        proposition_text="The occupier must not spread slurry within 10 metres of water.",
        legal_subject="occupier",
        action="not spread slurry within 10 metres of water",
    )
    raw = json.loads(prop.model_dump_json())
    assert raw["is_compliance_relevant"] is True


def test_derive_compliance_and_anchor_matrix() -> None:
    assert derive_is_compliance_relevant(LegalEffectType.OBLIGATION) is True
    assert derive_is_compliance_relevant(LegalEffectType.CITATION) is False
    assert (
        derive_is_comparison_anchor(
            proposition_tier=PropositionTier.INSTRUMENT_METADATA,
            legal_effect_type=LegalEffectType.EXTENT,
        )
        is False
    )
    assert (
        derive_is_comparison_anchor(
            proposition_tier=PropositionTier.SCOPE_RULE,
            legal_effect_type=LegalEffectType.APPLICATION_SCOPE,
        )
        is True
    )


@pytest.mark.parametrize(
    "text,expected_effect",
    [
        ("These Regulations may be cited as the X.", LegalEffectType.CITATION),
        ("These Regulations come into force on 1 May.", LegalEffectType.COMMENCEMENT),
        ("These Regulations extend to England.", LegalEffectType.EXTENT),
        ("These Regulations apply to farms in Wales.", LegalEffectType.APPLICATION_SCOPE),
        ("'X' means Y.", LegalEffectType.DEFINITION),
        ("A person must comply.", LegalEffectType.OBLIGATION),
        ("No person shall discharge.", LegalEffectType.OBLIGATION),
        ("An occupier must not discharge.", LegalEffectType.PROHIBITION),
        ("The Agency may inspect records.", LegalEffectType.INSPECTION),
        ("Bogus filler text only.", LegalEffectType.UNKNOWN),
    ],
)
def test_effect_heuristic_matrix(text: str, expected_effect: LegalEffectType) -> None:
    effect = derive_legal_effect_type(proposition_text=text, legal_subject="subject", action="act")
    assert effect == expected_effect


def test_obligation_wins_over_in_accordance_with_cross_reference_phrase() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "The occupier must establish the total amount of nitrogen in livestock manure "
            "by using the table in Part 1 of Schedule 3 or by sampling in accordance with Part 2."
        ),
        legal_subject="occupier",
        action="establish the total amount of nitrogen",
        extraction_meta={"provision_type": "cross_reference"},
    )
    assert effect is LegalEffectType.OBLIGATION


def test_slurry_table_available_nitrogen_percentage_is_definition() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "For cattle slurry spread on or after 1st January 2014, "
            "the available nitrogen is 40% of the nitrogen content."
        ),
        legal_subject="available nitrogen in cattle slurry",
        action="is",
    )
    assert effect is LegalEffectType.DEFINITION


def test_schedule_livestock_manure_coefficient_is_definition() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "A dairy cow after first calf with an annual milk yield more than 9000 litres "
            "produces 64 litres of manure, 315 grams of nitrogen, and 142 grams of phosphate daily."
        ),
        legal_subject="dairy cow",
        action="produces",
    )
    assert effect is LegalEffectType.DEFINITION


def test_spreading_permitted_is_permission_not_unknown() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "Spreading organic manure with high readily available nitrogen on tillage land "
            "with sandy or shallow soil is permitted between 1 August and 15 September inclusive."
        ),
        legal_subject="spreading",
        action="is permitted",
    )
    assert effect is LegalEffectType.PERMISSION


def test_incorporation_by_reference_is_cross_reference() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "The provisions of the Environmental Civil Sanctions (England) Order 2010 "
            "relating to the sanctions in regulation 13(1) apply as if they were provisions of these Regulations."
        ),
        legal_subject="provisions",
        action="apply as if",
    )
    assert effect is LegalEffectType.CROSS_REFERENCE


def test_amending_substitution_is_cross_reference() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "In the Environmental Permitting (England and Wales) Regulations 2016, "
            "Schedule 2, paragraph 17(2)(b), the reference to 'the Nitrate Pollution Prevention "
            "(Wales) Regulations 2013' is substituted with a reference to these Regulations."
        ),
        legal_subject="reference",
        action="is substituted",
    )
    assert effect is LegalEffectType.CROSS_REFERENCE


def test_enforcement_authority_statement_not_compliance_relevant() -> None:
    r = _classify(
        proposition_text=(
            "The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021 "
            "are enforced by Natural Resources Wales."
        ),
        legal_subject="These Regulations",
        action="are enforced by",
        label="Enforcement by NRW",
    )
    assert r.legal_effect_type == LegalEffectType.ENFORCEMENT
    assert r.is_compliance_relevant is False


def test_holding_area_exclusion_no_account_is_taken_is_definition() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "In calculating the area of the holding for the purposes of ascertaining "
            "the amount of nitrogen permitted to be spread on the holding, "
            "no account is taken of surface waters, any hardstanding, buildings, or roads."
        ),
        legal_subject="area of the holding",
        action="is calculated",
    )
    assert effect is LegalEffectType.DEFINITION


def test_external_meaning_given_by_is_definition_even_with_cross_reference_provision_type() -> None:
    effect = derive_legal_effect_type(
        proposition_text="Agricultural has the meaning given by section 109(3) of the Agriculture Act 1947.",
        legal_subject="agricultural",
        action="has the meaning given by",
        extraction_meta={"provision_type": "cross_reference"},
    )
    assert effect is LegalEffectType.DEFINITION


def test_may_apply_for_derogation_is_permission_not_application_scope() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "The occupier of a holding may apply to the Agency for a derogation "
            "where 80% or more of the agricultural area is sown with grass."
        ),
        legal_subject="occupier of a holding",
        action="may apply to the Agency for a derogation",
    )
    assert effect is LegalEffectType.PERMISSION


def test_means_a_derogation_is_definition_not_derogation_effect() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "A derogation means a derogation granted under this Part from the limit "
            "on the total amount of nitrogen in livestock manure."
        ),
        legal_subject="derogation",
        action="means",
    )
    assert effect is LegalEffectType.DEFINITION


def test_repair_definition_label_slurry_means_is_definition() -> None:
    r = _classify(
        proposition_text=(
            "Slurry means excreta produced by livestock (other than poultry) while in a yard or building."
        ),
        legal_subject="slurry",
        action="means",
        label="Definition: slurry",
    )
    assert r.legal_effect_type == LegalEffectType.DEFINITION
    assert r.proposition_tier == PropositionTier.DEFINITIONAL_RULE


def test_repair_definition_grass_includes_is_definition() -> None:
    r = _classify(
        proposition_text="Grass includes permanent grassland or temporary grassland.",
        legal_subject="grass",
        action="includes",
        label="Definition: grass",
    )
    assert r.legal_effect_type == LegalEffectType.DEFINITION


def test_cattle_slurry_nitrogen_percentage_is_definition() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "For cattle slurry, the available nitrogen for crop uptake in the growing season "
            "in which it is spread on land is 35% (40% before 2014)."
        ),
        legal_subject="available nitrogen in cattle slurry",
        action="is",
        label="Cattle slurry available nitrogen percentage (post-2014)",
    )
    assert effect is LegalEffectType.DEFINITION


def test_compliance_period_notice_is_obligation() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "The period for compliance stated in a regulation 30 notice is 28 days, "
            "or such longer period as is reasonable."
        ),
        legal_subject="period for compliance",
        action="is",
        label="Compliance period for regulation 30 notice",
    )
    assert effect is LegalEffectType.OBLIGATION


def test_greenhouse_land_exclusion_from_limit_is_derogation() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "The reference in paragraph (1) to the land on the holding does not include "
            "any land which is covered by a greenhouse for the whole of the period concerned."
        ),
        legal_subject="250kg nitrogen limit in paragraph (1)",
        action="does not include",
    )
    assert effect is LegalEffectType.DEROGATION


def test_regulation_does_not_apply_carveout_is_derogation() -> None:
    effect = derive_legal_effect_type(
        proposition_text="This regulation does not apply in a case where the requirements in paragraph (7) are met.",
        legal_subject="regulation 8",
        action="does not apply if",
    )
    assert effect is LegalEffectType.DEROGATION


def test_british_standard_equivalence_is_permission_not_unknown() -> None:
    effect = derive_legal_effect_type(
        proposition_text=(
            "A requirement for a silo or slurry storage tank to conform to a British Standard "
            "(in whole or in part) is satisfied if the silo or tank conforms to a standard "
            "that provides an equivalent level of protection and performance."
        ),
        legal_subject="requirement for silo or slurry storage tank",
        action="is satisfied if",
    )
    assert effect is LegalEffectType.PERMISSION
