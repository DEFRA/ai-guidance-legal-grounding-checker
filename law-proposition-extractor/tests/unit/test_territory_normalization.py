import pytest

from law_proposition_extractor_domain.territory_normalization import (
    coerce_source_jurisdiction_for_proposition,
    extract_territories_from_text,
    normalize_source_jurisdiction,
    normalize_territory_name,
    split_territory_list,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("england", "England"),
        ("WALES", "Wales"),
        ("scotland", "Scotland"),
        ("northern ireland", "Northern Ireland"),
        ("great britain", "Great Britain"),
        ("united kingdom", "United Kingdom"),
        ("uk", "United Kingdom"),
        ("gb", "Great Britain"),
        ("eu", "EU"),
        ("european union", "EU"),
        ("member state", "Member State"),
        ("member states", "Member State"),
        ("the union", "EU"),
        ("Union", "EU"),
        ("bogusshire", None),
        ("", None),
    ],
)
def test_normalize_territory_name(raw: str, expected: str | None) -> None:
    assert normalize_territory_name(raw) == expected


def test_normalize_source_jurisdiction_coarse_uk() -> None:
    assert normalize_source_jurisdiction("GB") == "UK"
    assert normalize_source_jurisdiction("England") == "England"


def test_split_territory_list_england_and_wales() -> None:
    assert split_territory_list("England and Wales") == ["England", "Wales"]


def test_extract_extent_england_and_wales() -> None:
    places = extract_territories_from_text(
        "These Regulations extend to England and Wales.",
        context="extent",
    )
    assert places == ["England", "Wales"]


def test_extract_application_scope_england_only() -> None:
    places = extract_territories_from_text(
        "These Regulations apply to agricultural land in England.",
        context="application_scope",
    )
    assert places == ["England"]


def test_extract_mention_does_not_guess_from_vague_text() -> None:
    assert extract_territories_from_text("Operators must keep records.", context="mention") == []


def test_coerce_source_jurisdiction_uk_hosted_england_statute() -> None:
    assert (
        coerce_source_jurisdiction_for_proposition(
            coarse_jurisdiction="UK",
            explicit_source_jurisdiction=None,
        )
        == "UK"
    )
    assert (
        coerce_source_jurisdiction_for_proposition(
            coarse_jurisdiction="England",
            explicit_source_jurisdiction=None,
        )
        == "UK"
    )


def test_coerce_source_jurisdiction_explicit_eu() -> None:
    assert (
        coerce_source_jurisdiction_for_proposition(
            coarse_jurisdiction="EU",
            explicit_source_jurisdiction="EU",
        )
        == "EU"
    )
