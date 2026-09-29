"""Unit tests for external standard and guidance reference classification."""

from __future__ import annotations

from law_proposition_extractor_pipeline.external_reference_classification import (
    extract_external_references,
    filter_internal_reference_targets,
    internal_locator_subsumed_by_external,
)

_BS_PART_50_TEXT = (
    "The walls of any pipes must be protected against corrosion in accordance with "
    "paragraph 7 of the code of practice on buildings and structures for agriculture "
    "published by the British Standards Institution and numbered BS 5502: Part 50:1993."
)

_BS_PART_22_TEXT = (
    "The retaining walls must be designed in the manner indicated by paragraphs 15.6.1 to "
    "15.6.3 of the code of practice on buildings and structures for agriculture published "
    "by the British Standards Institution and numbered BS 5502: Part 22: 1993."
)

_BS_PART_22_PAREN_TEXT = (
    "Retaining walls of a silo must be capable of withstanding minimum wall loadings "
    "calculated on the assumptions and in the manner indicated by paragraph 15.6.1 to "
    "15.6.3 of BS 5502 (Part 22: 1993)."
)

_BS_PART_50_PAREN_TEXT = (
    "The walls of any pipes must be protected against corrosion in accordance with "
    "paragraph 7.2 of BS 5502 (Part 50: 1993)."
)

_RB209_TEXT = (
    "The occupier must establish nitrogen availability by reference to the values given "
    "in the Nutrient Management Guide (RB209), or by sampling."
)


def test_extract_bs_5502_part_50_with_paragraph() -> None:
    refs = extract_external_references(_BS_PART_50_TEXT)
    assert len(refs) == 1
    assert refs[0]["kind"] == "external_standard_reference"
    assert refs[0]["resolution_status"] == "external_reference"
    assert refs[0]["locator"] == "BS 5502: Part 50:1993, paragraph 7"
    assert refs[0]["proposition_ids"] == []


def test_extract_bs_5502_part_22_paragraph_range() -> None:
    refs = extract_external_references(_BS_PART_22_TEXT)
    assert len(refs) == 1
    assert "BS 5502: Part 22: 1993" in refs[0]["locator"]
    assert "15.6.1 to 15.6.3" in refs[0]["locator"]


def test_extract_rb209_guidance_reference() -> None:
    refs = extract_external_references(_RB209_TEXT)
    assert len(refs) == 1
    assert refs[0]["kind"] == "external_guidance_reference"
    assert refs[0]["locator"] == "Nutrient Management Guide (RB209)"


def test_paragraph_seven_subsumed_when_part_of_bs_reference() -> None:
    refs = extract_external_references(_BS_PART_50_TEXT)
    assert internal_locator_subsumed_by_external(
        "paragraph 7",
        text=_BS_PART_50_TEXT,
        external_refs=refs,
    )


def test_filter_drops_paragraph_target_inside_bs_cite() -> None:
    refs = extract_external_references(_BS_PART_50_TEXT)
    filtered = filter_internal_reference_targets(
        ["paragraph 7", "regulation 8"],
        text=_BS_PART_50_TEXT,
        external_refs=refs,
    )
    assert filtered == ["regulation 8"]


def test_extract_bs_5502_paren_part_22_paragraph_range() -> None:
    refs = extract_external_references(_BS_PART_22_PAREN_TEXT)
    assert len(refs) == 1
    assert refs[0]["kind"] == "external_standard_reference"
    assert refs[0]["locator"] == "BS 5502 (Part 22: 1993), paragraph 15.6.1 to 15.6.3"


def test_extract_bs_5502_paren_part_50_with_decimal_paragraph() -> None:
    refs = extract_external_references(_BS_PART_50_PAREN_TEXT)
    assert len(refs) == 1
    assert refs[0]["locator"] == "BS 5502 (Part 50: 1993), paragraph 7.2"


def test_paragraph_fifteen_subsumed_for_paren_bs_reference() -> None:
    refs = extract_external_references(_BS_PART_22_PAREN_TEXT)
    assert internal_locator_subsumed_by_external(
        "paragraph 15",
        text=_BS_PART_22_PAREN_TEXT,
        external_refs=refs,
    )


def test_filter_drops_broad_paragraph_target_for_paren_bs_cite() -> None:
    refs = extract_external_references(_BS_PART_22_PAREN_TEXT)
    filtered = filter_internal_reference_targets(
        ["paragraph 15"],
        text=_BS_PART_22_PAREN_TEXT,
        external_refs=refs,
    )
    assert filtered == []


def test_extract_bare_bs_5502_in_accordance_with() -> None:
    refs = extract_external_references("Must be built in accordance with BS 5502.")
    assert len(refs) == 1
    assert refs[0]["locator"] == "BS 5502"


def test_extract_bare_bs_5502_designed_and_constructed() -> None:
    text = (
        "Any part of an effluent tank installed below ground level must be designed "
        "and constructed in accordance with BS 5502 so that with proper maintenance "
        "it is likely to satisfy the requirements of paragraphs 4 and 5 for at least "
        "20 years."
    )
    refs = extract_external_references(text)
    assert len(refs) == 1
    assert refs[0]["kind"] == "external_standard_reference"
    assert refs[0]["locator"] == "BS 5502"


def test_extract_bare_bs_8007_constructed_to() -> None:
    refs = extract_external_references("The tank must be constructed to BS 8007.")
    assert len(refs) == 1
    assert refs[0]["locator"] == "BS 8007"


def test_extract_bare_bs_en_iso_9001_comply_with() -> None:
    refs = extract_external_references("The occupier must comply with BS EN ISO 9001.")
    assert len(refs) == 1
    assert refs[0]["locator"] == "BS EN ISO 9001"


def test_specific_bs_reference_suppresses_bare_duplicate() -> None:
    refs = extract_external_references(
        "Must follow BS 5502: Part 50:1993, paragraph 7 for corrosion protection."
    )
    assert len(refs) == 1
    assert refs[0]["locator"] == "BS 5502: Part 50:1993, paragraph 7"


def test_paren_bs_reference_suppresses_bare_duplicate() -> None:
    refs = extract_external_references(_BS_PART_50_PAREN_TEXT)
    assert len(refs) == 1
    assert "BS 5502 (Part 50: 1993)" in refs[0]["locator"]


def test_internal_legal_locators_not_misclassified_as_external() -> None:
    assert extract_external_references("Must act in accordance with regulation 12.") == []
    assert extract_external_references("Must act in accordance with paragraph 7.") == []
    assert extract_external_references("Must comply with Part 2 of Schedule 3.") == []
