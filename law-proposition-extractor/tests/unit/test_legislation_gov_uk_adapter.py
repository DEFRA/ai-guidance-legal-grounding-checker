from pathlib import Path

from law_proposition_extractor_pipeline.sources import LegislationGovUkAuthorityAdapter, SourceIngestionService


def test_legislation_adapter_fetches_and_normalizes_single_data_xml_shape(tmp_path: Path) -> None:
    xml_payload = """
    <Legislation>
      <Title>Example Act 2024</Title>
      <LongTitle>An Act to illustrate a narrow integration path.</LongTitle>
      <ExplanatoryNotes>
        <P1>Explanatory Notes should not be treated as operative text.</P1>
      </ExplanatoryNotes>
      <Body>
        <P1 id="section-1">Section 1. Operators must maintain records.</P1>
        <P1 id="section-2">Section 2. The authority may inspect records on request.</P1>
      </Body>
    </Legislation>
    """

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "ukpga/2024/1",
                "version_id": "2024-01-01",
                "id": "src-uk-leg-001",
                "fragment_locator": "section:1",
            }
        ]
    )

    assert result.traces[0]["decision"] == "fetched_then_cached"
    assert result.traces[0]["adapter"] == "LegislationGovUkAuthorityAdapter"
    assert result.traces[0]["adapter_trace"]["http_status"] == 200
    assert result.sources[0].title == "Example Act 2024"
    assert result.sources[0].citation == "UKPGA 2024/1"
    assert result.sources[0].provenance == "authority.legislation_gov_uk"
    assert "Section 1. Operators must maintain records." in result.sources[0].authoritative_text
    assert "Explanatory Notes should not be treated as operative text." not in (
        result.sources[0].authoritative_text
    )
    # Raw fragment_locator input still takes precedence to preserve compatibility.
    assert result.sources[0].authoritative_locator == "section:1"
    assert result.sources[0].metadata["fragment_locators"] == ["xml:section-1", "xml:section-2"]
    assert result.sources[0].metadata["operative_chunk_count"] == 2
    assert result.snapshots[0].source_record_id == "src-uk-leg-001"
    assert result.fragments[0].locator == "section:1"


def test_legislation_adapter_emits_structural_schedule_fragments(tmp_path: Path) -> None:
    xml_payload = """
    <Legislation DocumentURI="http://www.legislation.gov.uk/ssi/2019/71">
      <Title>Example SSI</Title>
      <Body id="body">
        <P1 id="regulation-1">
          <Pnumber>1.</Pnumber>
          <Text>These Regulations come into force on 1 April 2019.</Text>
        </P1>
        <P1 id="schedule-1">
          <Title>Schedule 1</Title>
          <Text>Inspection powers.</Text>
        </P1>
        <P2 id="schedule-1-paragraph-3">
          <Pnumber>3.</Pnumber>
          <Text>Inspectors may enter premises for enforcement.</Text>
        </P2>
      </Body>
    </Legislation>
    """

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "ssi/2019/71",
                "version_id": "2024-01-01",
                "id": "src-ssi-leg-071",
            }
        ]
    )

    locators = [frag.locator for frag in result.fragments]
    assert "regulation:1" in locators
    assert "schedule:1" in locators
    assert "schedule:1:paragraph:3" in locators
    by_locator = {frag.locator: frag for frag in result.fragments}
    assert "Schedule 1" not in by_locator["regulation:1"].fragment_text
    assert by_locator["schedule:1:paragraph:3"].parent_fragment_id == by_locator["schedule:1"].id
    assert by_locator["schedule:1"].metadata.get("source_path") == "schedule/1"
    assert by_locator["schedule:1:paragraph:3"].metadata.get("fragment_kind") in {
        "amendment_provision",
        "operative_provision",
    }


def test_legislation_structural_fragment_serialisation_preserves_clml_boundaries() -> None:
    """Regression: structure-aware serializer keeps paragraph/list labels separate from prose."""
    from xml.etree import ElementTree

    from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments

    xml_payload = """
    <Legislation DocumentURI="http://www.legislation.gov.uk/wsi/2021/1">
      <Body>
        <P2 id="schedule-1a-paragraph-18">
          <Pnumber>18.</Pnumber>
          <P3>
            <Pnumber>1</Pnumber>
            <Text>The occupier must—</Text>
            <P4>
              <Pnumber>a</Pnumber>
              <Text>make a record of livestock manure, and</Text>
            </P4>
            <P4>
              <Pnumber>b</Pnumber>
              <Text>assess and record the amount of nitrogen.</Text>
            </P4>
          </P3>
        </P2>
      </Body>
    </Legislation>
    """
    root = ElementTree.fromstring(xml_payload)
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="http://www.legislation.gov.uk/wsi/2021/1/data.xml",
    )
    by_locator = {row["locator"]: row["text"] for row in rows}
    text = by_locator["schedule:1a:paragraph:18"]

    assert text.startswith("18(1) The occupier must—")
    assert "(a) make a record of livestock manure, and (b) assess and record" in text
    assert "181The occupier" not in text
    assert "amake a record" not in text
    assert "andbassess" not in text


def test_legislation_adapter_emits_regulation_and_article_paragraph_fragments(
    tmp_path: Path,
) -> None:
    xml_payload = """
    <Legislation DocumentURI="http://www.legislation.gov.uk/wsi/2021/77">
      <Title>Example WSI</Title>
      <Body id="body">
        <P1 id="regulation-36">
          <Pnumber>36.</Pnumber>
          <Text>Regulation 36 applies to nitrogen accounting.</Text>
          <P2 id="regulation-36-1">
            <Pnumber>1</Pnumber>
            <Text>Paragraph one of regulation 36.</Text>
          </P2>
          <P2 id="regulation-36-4">
            <Pnumber>4</Pnumber>
            <Text>The occupier must make a record of the calculations.</Text>
          </P2>
        </P1>
        <P1 id="article-12">
          <Pnumber>12.</Pnumber>
          <Text>Article 12 overview.</Text>
          <P2 id="article-12-2">
            <Pnumber>2</Pnumber>
            <Text>Article 12 paragraph two text.</Text>
          </P2>
        </P1>
        <P1 id="rule-5">
          <Pnumber>5.</Pnumber>
          <Text>Rule 5 overview.</Text>
          <P2 id="rule-5-3">
            <Pnumber>3</Pnumber>
            <Text>Rule 5 paragraph three text.</Text>
          </P2>
        </P1>
      </Body>
    </Legislation>
    """

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "wsi/2021/77",
                "version_id": "2024-01-01",
                "id": "src-wsi-reg-para",
            }
        ]
    )

    locators = [frag.locator for frag in result.fragments]
    assert "regulation:36" in locators
    assert "regulation:36:paragraph:1" in locators
    assert "regulation:36:paragraph:4" in locators
    assert "article:12" in locators
    assert "article:12:paragraph:2" in locators
    assert "rule:5" in locators
    assert "rule:5:paragraph:3" in locators

    by_locator = {frag.locator: frag for frag in result.fragments}
    assert "Paragraph one of regulation 36." in by_locator["regulation:36:paragraph:1"].fragment_text
    assert "Regulation 36 applies" not in by_locator["regulation:36:paragraph:4"].fragment_text
    assert by_locator["regulation:36:paragraph:4"].fragment_text.startswith(
        "(4) The occupier must make a record"
    )
    assert by_locator["regulation:36:paragraph:4"].parent_fragment_id == by_locator["regulation:36"].id
    assert by_locator["article:12:paragraph:2"].parent_fragment_id == by_locator["article:12"].id
    assert by_locator["rule:5:paragraph:3"].parent_fragment_id == by_locator["rule:5"].id


def test_legislation_adapter_does_not_duplicate_schedule_paragraph_fragments(
    tmp_path: Path,
) -> None:
    xml_payload = """
    <Legislation DocumentURI="http://www.legislation.gov.uk/wsi/2021/77">
      <Body id="body">
        <P1 id="regulation-36">
          <Pnumber>36.</Pnumber>
          <Text>Regulation 36 body.</Text>
          <P2 id="regulation-36-4">
            <Pnumber>4</Pnumber>
            <Text>Regulation 36 paragraph four.</Text>
          </P2>
        </P1>
        <P1 id="schedule-1">
          <Title>Schedule 1</Title>
        </P1>
        <P2 id="schedule-1-paragraph-3">
          <Pnumber>3.</Pnumber>
          <Text>Schedule 1 paragraph three.</Text>
        </P2>
        <P2 id="schedule-1-3">
          <Pnumber>3.</Pnumber>
          <Text>Duplicate schedule paragraph three via numeric id.</Text>
        </P2>
      </Body>
    </Legislation>
    """

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "wsi/2021/77",
                "version_id": "2024-01-01",
                "id": "src-wsi-dedupe",
            }
        ]
    )

    schedule_para_locators = [
        frag.locator for frag in result.fragments if frag.locator == "schedule:1:paragraph:3"
    ]
    assert len(schedule_para_locators) == 1
    assert "regulation:36:paragraph:4" in [frag.locator for frag in result.fragments]


def test_legislation_adapter_emits_regulation_paragraphs_from_live_clml_ppara_wrappers(
    tmp_path: Path,
) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "regulation_paragraph_fragmentation"
        / "wsi_2021_77_regulation_36_live_clml.xml"
    )
    xml_payload = fixture_path.read_text(encoding="utf-8")

    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "wsi/2021/77",
                "version_id": "2024-01-01",
                "id": "src-wsi-live-clml",
            }
        ]
    )

    locators = [frag.locator for frag in result.fragments]
    assert "regulation:36:paragraph:1" in locators
    assert "regulation:36:paragraph:4" in locators
    assert "schedule:1:paragraph:3" in locators
    by_locator = {frag.locator: frag for frag in result.fragments}
    assert "occupier must make a record" in by_locator["regulation:36"].fragment_text
    assert by_locator["regulation:36"].fragment_text.startswith("36.")
