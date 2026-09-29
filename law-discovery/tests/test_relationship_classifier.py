from __future__ import annotations

from law_discovery.models import CandidateSource
from law_discovery.relationship_classifier import (
    are_title_jurisdictions_compatible,
    classify_relationship_from_title,
    distinctive_title_terms,
    extract_title_jurisdiction_signals,
    normalise_title_for_relationship,
)


def _seed(
    *,
    source_id: str = "uksi/2009/1741",
    title: str = "Horse Passports Regulations 2009",
) -> CandidateSource:
    return CandidateSource(source_id=source_id, title=title)


def test_normalise_title_for_relationship() -> None:
    assert normalise_title_for_relationship("Foo (Bar) Act!") == "foo bar act"


def test_distinctive_title_terms_skips_stopwords() -> None:
    terms = distinctive_title_terms("The Horse Passports Regulations 2009")
    assert "horse" in terms
    assert "the" not in terms


def test_amendment_classified_as_amended_by() -> None:
    candidate = CandidateSource(
        source_id="uksi/2015/999",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
    )
    relationship = classify_relationship_from_title(_seed(), candidate)
    assert relationship is not None
    assert relationship.relationship_type == "amended_by"
    assert relationship.confidence in {"high", "medium", "low"}


def test_commencement_classified_as_commenced_by() -> None:
    candidate = CandidateSource(
        source_id="uksi/2010/1",
        title="Horse Passports Regulations 2009 Commencement Order 2010",
    )
    relationship = classify_relationship_from_title(_seed(), candidate)
    assert relationship is not None
    assert relationship.relationship_type == "commenced_by"


def test_correction_slip_classified_as_corrected_by() -> None:
    candidate = CandidateSource(
        source_id="corr/1",
        title="Horse Passports Regulations 2009 correction slip",
    )
    relationship = classify_relationship_from_title(_seed(), candidate)
    assert relationship is not None
    assert relationship.relationship_type == "corrected_by"


def test_explanatory_memorandum_classified_as_explained_by() -> None:
    candidate = CandidateSource(
        source_id="em/1",
        title="Horse Passports Regulations 2009 explanatory memorandum",
    )
    relationship = classify_relationship_from_title(_seed(), candidate)
    assert relationship is not None
    assert relationship.relationship_type == "explained_by"


def test_guidance_classified_as_guidance_for() -> None:
    candidate = CandidateSource(
        source_id="guid/1",
        title="Horse Passports Regulations 2009 guidance",
    )
    relationship = classify_relationship_from_title(_seed(), candidate)
    assert relationship is not None
    assert relationship.relationship_type == "guidance_for"


def test_nvz_designation_not_classified_as_amended_by() -> None:
    seed = CandidateSource(
        source_id="uksi/2015/668",
        title="Nitrates Regulations 2015",
    )
    candidate = CandidateSource(
        source_id="uksi/2017/123",
        title="Designation of Nitrate Vulnerable Zones (England) Order 2017",
    )
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is None or relationship.relationship_type != "amended_by"


def test_loose_category_match_returns_none() -> None:
    seed = CandidateSource(
        source_id="uksi/2015/668",
        title="Nitrates Regulations 2015",
    )
    candidate = CandidateSource(
        source_id="ukpga/1963/2",
        title="Betting, Gaming and Lotteries Act 1963",
    )
    assert classify_relationship_from_title(seed, candidate) is None


def test_unrelated_candidate_returns_none() -> None:
    candidate = CandidateSource(
        source_id="ukpga/1963/2",
        title="Betting, Gaming and Lotteries Act 1963",
    )
    assert classify_relationship_from_title(_seed(), candidate) is None


_NVZ_ENGLAND_WALES_SEED = (
    "The Action Programme for Nitrate Vulnerable Zones (England and Wales) Regulations 1998"
)
_NVZ_SCOTLAND_SEED = (
    "The Action Programme for Nitrate Vulnerable Zones (Scotland) Regulations 1998"
)
_NVZ_WALES_AMENDMENT = (
    "The Action Programme for Nitrate Vulnerable Zones (Amendment) (Wales) Regulations 2003"
)
_NVZ_SCOTLAND_AMENDMENT = (
    "The Action Programme for Nitrate Vulnerable Zones (Scotland) Amendment Regulations 2013"
)
_NVZ_NI_AMENDMENT = "Nitrates Action Programme (Amendment) Regulations (Northern Ireland) 2008"


def test_extract_title_jurisdiction_signals() -> None:
    assert extract_title_jurisdiction_signals(_NVZ_ENGLAND_WALES_SEED) == {
        "england_and_wales",
        "england",
        "wales",
    }
    assert extract_title_jurisdiction_signals(_NVZ_SCOTLAND_SEED) == {"scotland"}
    assert extract_title_jurisdiction_signals(_NVZ_WALES_AMENDMENT) == {"wales"}
    assert extract_title_jurisdiction_signals(_NVZ_NI_AMENDMENT) == {"northern_ireland"}
    assert extract_title_jurisdiction_signals("Foo Great Britain Order 2020") == {
        "great_britain"
    }
    assert extract_title_jurisdiction_signals("Foo (UK) Regulations 2020") == {"uk"}


def test_are_title_jurisdictions_compatible() -> None:
    assert are_title_jurisdictions_compatible(_NVZ_ENGLAND_WALES_SEED, _NVZ_WALES_AMENDMENT)
    assert not are_title_jurisdictions_compatible(_NVZ_SCOTLAND_SEED, _NVZ_WALES_AMENDMENT)
    assert are_title_jurisdictions_compatible(_NVZ_SCOTLAND_SEED, _NVZ_SCOTLAND_AMENDMENT)
    assert not are_title_jurisdictions_compatible(
        _NVZ_ENGLAND_WALES_SEED,
        _NVZ_NI_AMENDMENT,
    )
    assert are_title_jurisdictions_compatible(
        "Slurry Controls (Great Britain) Regulations 2010",
        "Slurry Controls (Scotland) Amendment Regulations 2015",
    )
    assert are_title_jurisdictions_compatible(
        "Slurry Controls (UK) Regulations 2010",
        "Slurry Controls (Wales) Amendment Regulations 2015",
    )


def test_wales_amendment_relates_to_england_and_wales_seed() -> None:
    seed = CandidateSource(source_id="uksi/1998/1202", title=_NVZ_ENGLAND_WALES_SEED)
    candidate = CandidateSource(source_id="wsi/2003/1852", title=_NVZ_WALES_AMENDMENT)
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is not None
    assert relationship.relationship_type == "amended_by"


def test_wales_amendment_does_not_relate_to_scotland_seed() -> None:
    seed = CandidateSource(source_id="uksi/1998/2927", title=_NVZ_SCOTLAND_SEED)
    candidate = CandidateSource(source_id="wsi/2003/1852", title=_NVZ_WALES_AMENDMENT)
    assert classify_relationship_from_title(seed, candidate) is None


def test_scotland_amendment_relates_to_scotland_seed() -> None:
    seed = CandidateSource(source_id="uksi/1998/2927", title=_NVZ_SCOTLAND_SEED)
    candidate = CandidateSource(
        source_id="ssi/2013/1",
        title=_NVZ_SCOTLAND_AMENDMENT,
    )
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is not None
    assert relationship.relationship_type == "amended_by"


def test_northern_ireland_amendment_does_not_relate_to_england_and_wales_seed() -> None:
    seed = CandidateSource(source_id="uksi/1998/1202", title=_NVZ_ENGLAND_WALES_SEED)
    candidate = CandidateSource(source_id="nisr/2008/1", title=_NVZ_NI_AMENDMENT)
    assert classify_relationship_from_title(seed, candidate) is None


def test_great_britain_seed_can_relate_to_scotland_amendment() -> None:
    seed = CandidateSource(
        source_id="uksi/2010/1",
        title="Slurry Storage (Great Britain) Regulations 2010",
    )
    candidate = CandidateSource(
        source_id="ssi/2015/1",
        title="Slurry Storage (Scotland) Amendment Regulations 2015",
    )
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is not None
    assert relationship.relationship_type == "amended_by"


def test_uk_seed_can_relate_to_wales_amendment() -> None:
    seed = CandidateSource(
        source_id="uksi/2010/1",
        title="Slurry Storage (UK) Regulations 2010",
    )
    candidate = CandidateSource(
        source_id="wsi/2015/1",
        title="Slurry Storage (Wales) Amendment Regulations 2015",
    )
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is not None
    assert relationship.relationship_type == "amended_by"
