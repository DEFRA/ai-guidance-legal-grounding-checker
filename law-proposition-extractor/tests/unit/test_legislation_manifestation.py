from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import pytest
from law_proposition_extractor_domain import SourceManifestationBasis, SourceManifestationType, SourceSnapshot
from law_proposition_extractor_pipeline.sources.adapters import LegislationGovUkAuthorityAdapter, SourceFetchRequest
from law_proposition_extractor_pipeline.sources.legislation_manifestation import (
    parse_legislation_manifestation_metadata,
    parse_legislation_request_url,
    resolve_manifestation_provenance,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "legislation_manifestation"


def _load(name: str) -> ElementTree.Element:
    return ElementTree.fromstring((FIXTURES / name).read_text(encoding="utf-8"))


class TestRequestUrlParsing:
    def test_point_in_time_url_records_requested_as_of_date(self) -> None:
        hints = parse_legislation_request_url(
            "https://www.legislation.gov.uk/eur/2009/1224/2020-12-31/data.xml"
        )
        assert hints.requested_manifestation == SourceManifestationType.POINT_IN_TIME
        assert hints.requested_as_of_date == date(2020, 12, 31)
        assert any(item["field"] == "path_version_date" for item in hints.evidence)

    def test_current_url_does_not_invent_as_of_date(self) -> None:
        hints = parse_legislation_request_url(
            "https://www.legislation.gov.uk/eur/2009/1224/data.xml"
        )
        assert hints.requested_manifestation is None
        assert hints.requested_as_of_date is None

    def test_original_version_url_is_explicit(self) -> None:
        for keyword in ("enacted", "adopted", "made"):
            hints = parse_legislation_request_url(
                f"https://www.legislation.gov.uk/ukpga/2021/1/{keyword}/data.xml"
            )
            assert hints.requested_manifestation == SourceManifestationType.ORIGINAL
            assert hints.requested_as_of_date is None

    def test_unrelated_query_string_ignored(self) -> None:
        hints = parse_legislation_request_url(
            "https://www.legislation.gov.uk/eur/2009/1224/data.xml?view=extent&foo=bar"
        )
        assert hints.requested_manifestation is None
        assert hints.requested_as_of_date is None

    def test_url_parsing_is_deterministic(self) -> None:
        url = "https://www.legislation.gov.uk/eur/2009/1224/2020-12-31/data.xml"
        assert parse_legislation_request_url(url) == parse_legislation_request_url(url)


class TestSourceMetadataParsing:
    def test_explicit_original_metadata(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("original_adopted.xml"))
        assert hints.resolved_manifestation == SourceManifestationType.ORIGINAL
        assert hints.resolved_as_of_date is None
        assert hints.document_status == "final"

    def test_explicit_revised_metadata(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("revised_current.xml"))
        assert hints.resolved_manifestation == SourceManifestationType.REVISED
        assert hints.source_revision_date == date(2025, 2, 27)
        # Revision stamp is not a legal as-of date for current revised text.
        assert hints.resolved_as_of_date is None

    def test_explicit_point_in_time_metadata(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("point_in_time.xml"))
        assert hints.resolved_manifestation == SourceManifestationType.POINT_IN_TIME
        assert hints.resolved_as_of_date == date(2020, 12, 31)
        # Provision-level RestrictStartDate 2019-04-14 must not win.
        assert hints.resolved_as_of_date != date(2019, 4, 14)

    def test_explicit_prospective_metadata(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("prospective.xml"))
        assert hints.resolved_manifestation == SourceManifestationType.PROSPECTIVE

    def test_missing_metadata_is_unknown(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("no_manifestation_metadata.xml"))
        assert hints.resolved_manifestation is None
        assert hints.resolved_as_of_date is None

    def test_dc_modified_is_not_legal_as_of(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("revised_current.xml"))
        assert hints.dc_modified == date(2025, 4, 4)
        assert hints.resolved_as_of_date is None

    def test_namespace_variant_enacted(self) -> None:
        hints = parse_legislation_manifestation_metadata(_load("enacted_namespace_variant.xml"))
        assert hints.resolved_manifestation == SourceManifestationType.ORIGINAL
        assert hints.document_status == "final"

    def test_conflict_uri_and_status(self) -> None:
        hints = parse_legislation_manifestation_metadata(
            _load("conflict_original_uri_revised_status.xml")
        )
        assert hints.resolved_manifestation is None
        assert hints.conflicts


class TestRequestVersusResolved:
    def test_requested_and_resolved_remain_distinct(self) -> None:
        prov = resolve_manifestation_provenance(
            requested_url="https://www.legislation.gov.uk/eur/2009/1224/2020-12-31/data.xml",
            xml_root=_load("point_in_time.xml"),
        )
        assert prov.requested_manifestation == SourceManifestationType.POINT_IN_TIME
        assert prov.resolved_manifestation == SourceManifestationType.POINT_IN_TIME
        assert prov.requested_as_of_date == date(2020, 12, 31)
        assert prov.resolved_as_of_date == date(2020, 12, 31)
        assert prov.manifestation_basis == SourceManifestationBasis.REQUEST_AND_SOURCE_METADATA

    def test_source_metadata_takes_precedence_for_unqualified_url(self) -> None:
        prov = resolve_manifestation_provenance(
            requested_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
            xml_root=_load("revised_current.xml"),
        )
        assert prov.requested_manifestation is None
        assert prov.manifestation_type == SourceManifestationType.REVISED
        assert prov.manifestation_basis == SourceManifestationBasis.SOURCE_METADATA
        assert prov.resolved_as_of_date is None
        assert prov.source_revision_date == date(2025, 2, 27)

    def test_request_only_does_not_claim_resolved(self) -> None:
        prov = resolve_manifestation_provenance(
            requested_url="https://www.legislation.gov.uk/ukpga/2021/1/enacted/data.xml",
            xml_root=_load("no_manifestation_metadata.xml"),
        )
        assert prov.requested_manifestation == SourceManifestationType.ORIGINAL
        assert prov.resolved_manifestation is None
        assert prov.manifestation_type == SourceManifestationType.UNKNOWN
        assert prov.manifestation_basis == SourceManifestationBasis.REQUEST_URL

    def test_conflicting_strong_evidence_yields_unknown(self) -> None:
        prov = resolve_manifestation_provenance(
            requested_url="https://www.legislation.gov.uk/eur/2009/1224/adopted/data.xml",
            xml_root=_load("conflict_original_uri_revised_status.xml"),
        )
        assert prov.manifestation_type == SourceManifestationType.UNKNOWN
        assert prov.conflicts

    def test_redirect_resolved_url_retained(self) -> None:
        prov = resolve_manifestation_provenance(
            requested_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
            resolved_url="https://www.legislation.gov.uk/eur/2009/1224/2020-12-31/data.xml",
            xml_root=_load("point_in_time.xml"),
        )
        assert prov.requested_url.endswith("/1224/data.xml")
        assert prov.resolved_url.endswith("/2020-12-31/data.xml")
        assert prov.manifestation_type == SourceManifestationType.POINT_IN_TIME


class TestAdapterAndPersistence:
    def test_adapter_persists_revised_manifestation_fields(self) -> None:
        xml = (FIXTURES / "revised_current.xml").read_text(encoding="utf-8")

        def fetch_xml(_url: str) -> tuple[str, dict]:
            return xml, {
                "status": 200,
                "content_type": "application/xml",
                "response_bytes": len(xml),
                "resolved_url": "https://www.legislation.gov.uk/eur/2009/1224/data.xml",
            }

        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml)
        result = adapter.fetch(
            SourceFetchRequest(
                authority="legislation_gov_uk",
                authority_source_id="eur/2009/1224",
                version_id="v1",
                expected_content_hash=None,
                raw_source={
                    "source_url": "https://www.legislation.gov.uk/eur/2009/1224/data.xml",
                    "retrieved_at": "2026-07-14T12:00:00Z",
                },
            )
        )
        payload = result.payload
        assert payload.manifestation_type == SourceManifestationType.REVISED
        assert payload.manifestation_basis == SourceManifestationBasis.SOURCE_METADATA
        assert payload.as_of_date is None
        assert payload.resolved_as_of_date is None
        assert payload.metadata["manifestation"]["type"] == "revised"

    def test_adapter_point_in_time_sets_as_of(self) -> None:
        xml = (FIXTURES / "point_in_time.xml").read_text(encoding="utf-8")

        def fetch_xml(_url: str) -> tuple[str, dict]:
            return xml, {"status": 200, "content_type": "application/xml", "response_bytes": 1}

        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fetch_xml)
        result = adapter.fetch(
            SourceFetchRequest(
                authority="legislation_gov_uk",
                authority_source_id="eur/2009/1224",
                version_id="v1",
                expected_content_hash=None,
                raw_source={
                    "source_url": (
                        "https://www.legislation.gov.uk/eur/2009/1224/2020-12-31/data.xml"
                    ),
                },
            )
        )
        assert result.payload.manifestation_type == SourceManifestationType.POINT_IN_TIME
        assert result.payload.requested_as_of_date == date(2020, 12, 31)
        assert result.payload.resolved_as_of_date == date(2020, 12, 31)
        assert result.payload.as_of_date == date(2020, 12, 31)

    def test_source_snapshot_serializes_manifestation_fields(self) -> None:
        from datetime import UTC, datetime

        snapshot = SourceSnapshot(
            id="snap-a-v1",
            source_record_id="src-a",
            version_id="v1",
            authoritative_text="text",
            provenance="authority.legislation_gov_uk",
            retrieved_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
            content_hash="abc",
            manifestation_type=SourceManifestationType.REVISED,
            manifestation_basis=SourceManifestationBasis.SOURCE_METADATA,
            manifestation_evidence=[
                {
                    "kind": "source_metadata",
                    "field": "DocumentStatus",
                    "value": "revised",
                    "source_location": "ukm:DocumentStatus/@Value",
                }
            ],
        )
        dumped = snapshot.model_dump(mode="json")
        assert dumped["manifestation_type"] == "revised"
        assert dumped["version_id"] == "v1"
        restored = SourceSnapshot.model_validate(
            {k: v for k, v in dumped.items() if k != "manifestation_type"}
        )
        assert restored.manifestation_type is None
        assert restored.version_id == "v1"

    def test_two_snapshots_can_differ(self) -> None:
        from datetime import UTC, datetime

        revised = SourceSnapshot(
            id="snap-a-revised",
            source_record_id="src-a",
            version_id="v1",
            authoritative_text="revised",
            provenance="authority.legislation_gov_uk",
            retrieved_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
            content_hash="a",
            manifestation_type=SourceManifestationType.REVISED,
            manifestation_basis=SourceManifestationBasis.SOURCE_METADATA,
        )
        pit = SourceSnapshot(
            id="snap-a-pit",
            source_record_id="src-a",
            version_id="v2",
            authoritative_text="pit",
            provenance="authority.legislation_gov_uk",
            retrieved_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
            content_hash="b",
            as_of_date=date(2020, 12, 31),
            manifestation_type=SourceManifestationType.POINT_IN_TIME,
            manifestation_basis=SourceManifestationBasis.REQUEST_AND_SOURCE_METADATA,
            requested_as_of_date=date(2020, 12, 31),
            resolved_as_of_date=date(2020, 12, 31),
        )
        assert revised.manifestation_type != pit.manifestation_type
        assert revised.source_record_id == pit.source_record_id

    def test_malformed_xml_metadata_does_not_crash(self) -> None:
        root = ElementTree.fromstring(
            "<Legislation DocumentURI='http://www.legislation.gov.uk/eur/2009/1224'>"
            "<Metadata><DocumentStatus/></Metadata></Legislation>"
        )
        hints = parse_legislation_manifestation_metadata(root)
        assert hints.resolved_manifestation is None


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("original_adopted.xml", SourceManifestationType.ORIGINAL),
        ("revised_current.xml", SourceManifestationType.REVISED),
        ("point_in_time.xml", SourceManifestationType.POINT_IN_TIME),
        ("prospective.xml", SourceManifestationType.PROSPECTIVE),
    ],
)
def test_fixture_examples(filename: str, expected: SourceManifestationType) -> None:
    hints = parse_legislation_manifestation_metadata(_load(filename))
    assert hints.resolved_manifestation == expected
