import pytest
from law_proposition_extractor_pipeline.sources import (
    LegislationGovUkSourceSearchProvider,
    SourceSearchError,
    SourceSearchService,
)


def test_legislation_search_resolves_identifier_without_series() -> None:
    xml_index = {
        "https://www.legislation.gov.uk/eur/2016/429/data.xml": """
        <Legislation>
          <Title>Animal Health Law</Title>
        </Legislation>
        """,
    }

    def fake_fetch_xml(url: str) -> str:
        if url not in xml_index:
            raise ValueError("not found")
        return xml_index[url]

    provider = LegislationGovUkSourceSearchProvider(
        fetch_xml=fake_fetch_xml,
        fetch_html=lambda _: "",
    )
    result = provider.search(query="2016/429")
    assert len(result) == 1
    assert result[0].authority_source_id == "eur/2016/429"
    assert result[0].title == "Animal Health Law"
    assert result[0].jurisdiction == "EU"
    assert result[0].canonical_source_url == "https://www.legislation.gov.uk/eur/2016/429"


def test_legislation_search_resolves_from_legislation_url() -> None:
    xml_payload = """
    <Legislation>
      <Title>Animal Health Law</Title>
    </Legislation>
    """

    provider = LegislationGovUkSourceSearchProvider(
        fetch_xml=lambda _: xml_payload,
        fetch_html=lambda _: "",
    )
    result = provider.search(query="https://www.legislation.gov.uk/id/eur/2016/429")
    assert len(result) == 1
    assert result[0].authority_source_id == "eur/2016/429"


def test_legislation_search_by_title_uses_authority_results() -> None:
    html = """
    <html>
      <body>
        <a href="/id/eur/2016/429">Animal Health Law</a>
        <a href="/id/ukpga/1990/1">Other instrument</a>
      </body>
    </html>
    """
    xml_payloads = {
        "https://www.legislation.gov.uk/eur/2016/429/data.xml": (
            "<Legislation><Title>Animal Health Law</Title></Legislation>"
        ),
        "https://www.legislation.gov.uk/ukpga/1990/1/data.xml": (
            "<Legislation><Title>Some Act</Title></Legislation>"
        ),
    }
    provider = LegislationGovUkSourceSearchProvider(
        fetch_xml=lambda url: xml_payloads[url],
        fetch_html=lambda _: html,
    )
    result = provider.search(query="Animal Health Law", limit=5)
    assert len(result) == 2
    assert result[0].authority_source_id == "eur/2016/429"
    assert result[1].authority_source_id == "ukpga/1990/1"


def test_source_search_service_defaults_legislation_provider() -> None:
    provider = LegislationGovUkSourceSearchProvider(
        fetch_xml=lambda _: "<Legislation><Title>Animal Health Law</Title></Legislation>",
        fetch_html=lambda _: "",
    )
    service = SourceSearchService(providers={"legislation_gov_uk": provider})
    payload = service.search(query="eur/2016/429")
    assert payload["provider"] == "legislation_gov_uk"
    assert payload["count"] == 1
    assert payload["candidates"][0]["citation"] == "EUR 2016/429"


def test_legislation_search_provider_wraps_unexpected_errors() -> None:
    provider = LegislationGovUkSourceSearchProvider(
        fetch_xml=lambda _: "<Legislation><Title>x</Title></Legislation>",
        fetch_html=lambda _: (_ for _ in ()).throw(RuntimeError("network exploded")),
    )
    with pytest.raises(SourceSearchError):
        provider.search(query="Animal Health Law")
