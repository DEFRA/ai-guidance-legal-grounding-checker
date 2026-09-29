"""Unit tests for legislation.gov.uk provision URL mapping."""

from audit_assembler.legislation_gov_uk_url import (
    legislation_document_base_url,
    legislation_provision_url,
    provision_path_from_locator,
)


def test_strips_data_xml_and_rejects_non_legislation_hosts():
    assert (
        legislation_document_base_url(
            "https://www.legislation.gov.uk/eur/2013/1380/data.xml"
        )
        == "https://www.legislation.gov.uk/eur/2013/1380"
    )
    assert (
        legislation_document_base_url("https://example.com/eur/2013/1380/data.xml")
        is None
    )


def test_strips_contents_made_seed_tails():
    assert (
        legislation_document_base_url(
            "https://www.legislation.gov.uk/uksi/2015/668/contents/made"
        )
        == "https://www.legislation.gov.uk/uksi/2015/668"
    )
    assert (
        legislation_document_base_url(
            "https://www.legislation.gov.uk/uksi/2010/639/made"
        )
        == "https://www.legislation.gov.uk/uksi/2010/639"
    )


def test_maps_canonical_locators_to_provision_paths():
    assert provision_path_from_locator("article:10") == "/article/10"
    assert provision_path_from_locator("article:10:paragraph:1") == "/article/10/1"
    assert provision_path_from_locator("article:109:list:1-d-i") == "/article/109"
    assert (
        provision_path_from_locator("schedule:1:paragraph:2")
        == "/schedule/1/paragraph/2"
    )
    assert (
        provision_path_from_locator("regulation:4:paragraph:1") == "/regulation/4/1"
    )
    assert provision_path_from_locator("annex:ii") == "/annex/II"
    # Leaf subparagraphs collapse to the paragraph path (stable legis HTML).
    assert (
        provision_path_from_locator("regulation:31:paragraph:6:subparagraph:a")
        == "/regulation/31/6"
    )


def test_maps_free_text_locators():
    assert provision_path_from_locator("Article 1(1)") == "/article/1/1"
    assert provision_path_from_locator("regulation 4(1)") == "/regulation/4/1"
    assert (
        provision_path_from_locator("Schedule 1 paragraph 2")
        == "/schedule/1/paragraph/2"
    )


def test_builds_full_provision_urls_and_falls_back_to_instrument():
    assert (
        legislation_provision_url(
            "https://www.legislation.gov.uk/uksi/2015/668/contents/made",
            "regulation:31:paragraph:6:subparagraph:a",
        )
        == "https://www.legislation.gov.uk/uksi/2015/668/regulation/31/6"
    )
    assert (
        legislation_provision_url(
            "https://www.legislation.gov.uk/ukpga/2020/22/data.xml",
            "not a locator",
        )
        == "https://www.legislation.gov.uk/ukpga/2020/22"
    )
    assert legislation_provision_url("https://leg/1", "regulation:1") is None
