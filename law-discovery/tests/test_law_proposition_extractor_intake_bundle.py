from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_discovery.cli import app
from law_discovery.law_proposition_extractor_intake_bundle import make_law_proposition_extractor_intake_bundle
from law_discovery.models import (
    CandidateSource,
    SourceBundle,
    SourceRelationship,
    load_source_bundle,
    save_source_bundle,
)

runner = CliRunner()


def _sample_bundle() -> SourceBundle:
    return SourceBundle(
        bundle_id="original-bundle-id",
        category_id="test_category",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        principal_sources=[
            CandidateSource(
                source_id="p1",
                title="Principal 1",
                review_status="accepted",
            ),
            CandidateSource(
                source_id="p2",
                title="Principal 2",
                review_status="accepted",
            ),
            CandidateSource(
                source_id="p3",
                title="Principal parked",
                review_status="parked",
            ),
        ],
        amending_sources=[
            CandidateSource(
                source_id="a1",
                title="Amending 1",
                review_status="accepted",
            ),
            CandidateSource(
                source_id="a2",
                title="Amending 2",
                review_status="accepted",
            ),
            CandidateSource(
                source_id="a3",
                title="Amending needs research",
                review_status="needs_more_research",
            ),
        ],
        revocation_sources=[
            CandidateSource(
                source_id="r1",
                title="Revocation 1",
                review_status="accepted",
            ),
            CandidateSource(
                source_id="r2",
                title="Revocation needs research",
                review_status="needs_more_research",
            ),
        ],
        contextual_sources=[
            CandidateSource(source_id="c1", title="Context 1", review_status="accepted"),
            CandidateSource(source_id="c2", title="Context 2", review_status="parked"),
            CandidateSource(source_id="c3", title="Context 3", review_status="parked"),
        ],
        rejected_sources=[
            CandidateSource(source_id="x1", title="Rejected 1", review_status="rejected"),
            CandidateSource(source_id="x2", title="Rejected 2", review_status="rejected"),
        ],
        relationships=[
            SourceRelationship(
                relationship_id="rel-accepted",
                from_source_id="p1",
                to_source_id="a1",
                relationship_type="amended_by",
                review_status="accepted",
            ),
            SourceRelationship(
                relationship_id="rel-needs-research",
                from_source_id="p1",
                to_source_id="a3",
                relationship_type="amended_by",
                review_status="needs_more_research",
            ),
            SourceRelationship(
                relationship_id="rel-rejected",
                from_source_id="p2",
                to_source_id="a2",
                relationship_type="amended_by",
                review_status="rejected",
            ),
            SourceRelationship(
                relationship_id="rel-p2-a1",
                from_source_id="p2",
                to_source_id="a1",
                relationship_type="amended_by",
                review_status="accepted",
            ),
        ],
        metadata={"source_register_id": "reg-1"},
    )


def test_basic_filtering() -> None:
    result = make_law_proposition_extractor_intake_bundle(_sample_bundle())

    bundle = result.bundle
    assert len(bundle.principal_sources) == 2
    assert len(bundle.amending_sources) == 2
    assert len(bundle.revocation_sources) == 1
    assert bundle.contextual_sources == []
    assert bundle.rejected_sources == []
    assert len(bundle.relationships) == 2
    assert {rel.relationship_id for rel in bundle.relationships} == {
        "rel-accepted",
        "rel-p2-a1",
    }

    assert bundle.bundle_id != "original-bundle-id"
    assert bundle.category_id == "test_category"
    assert bundle.created_at > datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    intake = bundle.metadata["intake"]
    assert intake["kind"] == "judit_intake"
    assert intake["source_bundle_id"] == "original-bundle-id"
    assert intake["filter_policy"]["principal_sources"] == ["accepted"]
    assert intake["excluded_counts"] == {
        "principal_sources": 1,
        "amending_sources": 1,
        "revocation_sources": 1,
        "contextual_sources": 3,
        "rejected_sources": 2,
        "relationships": 2,
    }

    SourceBundle.model_validate(bundle.model_dump())


def test_principal_only_mode() -> None:
    result = make_law_proposition_extractor_intake_bundle(_sample_bundle(), principal_only=True)
    bundle = result.bundle

    assert len(bundle.principal_sources) == 2
    assert bundle.amending_sources == []
    assert bundle.revocation_sources == []
    assert bundle.contextual_sources == []
    assert bundle.rejected_sources == []
    assert bundle.relationships == []


def test_max_principal_sources_limits_relationships() -> None:
    result = make_law_proposition_extractor_intake_bundle(_sample_bundle(), max_principal_sources=1)
    bundle = result.bundle

    assert len(bundle.principal_sources) == 1
    assert bundle.principal_sources[0].source_id == "p1"
    assert len(bundle.relationships) == 1
    assert bundle.relationships[0].relationship_id == "rel-accepted"


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    bundle = _sample_bundle()
    input_path = tmp_path / "bundle.json"
    output_path = tmp_path / "intake.json"
    save_source_bundle(bundle, input_path)

    result = runner.invoke(
        app,
        [
            "make-law-proposition-extractor-intake-bundle",
            str(input_path),
            "--output",
            str(output_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Would write Law Proposition Extractor intake bundle to" in result.stdout
    assert "Principal sources: 2 / 3" in result.stdout
    assert not output_path.exists()


def test_cli_writes_valid_output(tmp_path: Path) -> None:
    bundle = _sample_bundle()
    input_path = tmp_path / "bundle.json"
    output_path = tmp_path / "intake.json"
    save_source_bundle(bundle, input_path)

    result = runner.invoke(
        app,
        [
            "make-law-proposition-extractor-intake-bundle",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output_path.exists()
    assert "Wrote Law Proposition Extractor intake bundle to" in result.stdout
    load_source_bundle(output_path)


def test_invalid_input_path_fails(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "make-law-proposition-extractor-intake-bundle",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code != 0
    assert "Source bundle file not found" in result.stderr


def test_invalid_bundle_json_fails(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text('{"not": "a bundle"}', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "make-law-proposition-extractor-intake-bundle",
            str(bad_path),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code != 0
    assert "Invalid SourceBundle JSON" in result.stderr


def test_input_bundle_is_not_mutated() -> None:
    bundle = _sample_bundle()
    original = bundle.model_dump()
    make_law_proposition_extractor_intake_bundle(bundle)
    assert bundle.model_dump() == original


def _jurisdiction_bundle() -> SourceBundle:
    return SourceBundle(
        bundle_id="jurisdiction-bundle-id",
        category_id="slurry_manure_agricultural_effluent",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        principal_sources=[
            CandidateSource(
                source_id="gb-wide",
                title="The Nitrate Pollution Prevention Regulations 2015",
                review_status="accepted",
                jurisdiction_extent=["England", "Wales", "Scotland", "Northern Ireland"],
                temporal_status="current",
                confidence="high",
            ),
            CandidateSource(
                source_id="ni-title",
                title="The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) Regulations (Northern Ireland) 2003",
                review_status="accepted",
                canonical_uri="http://www.legislation.gov.uk/id/uksi/2003/999",
            ),
            CandidateSource(
                source_id="ni-uri",
                title="Some Other Slurry Instrument",
                review_status="accepted",
                canonical_uri="http://www.legislation.gov.uk/id/nisr/2003/319",
            ),
        ],
        amending_sources=[
            CandidateSource(
                source_id="a-ni",
                title="Northern Ireland amendment",
                review_status="accepted",
            ),
        ],
        relationships=[
            SourceRelationship(
                relationship_id="rel-gb-a1",
                from_source_id="gb-wide",
                to_source_id="a-ni",
                relationship_type="amended_by",
                review_status="accepted",
            ),
            SourceRelationship(
                relationship_id="rel-gb-ni-uri",
                from_source_id="gb-wide",
                to_source_id="ni-uri",
                relationship_type="cites",
                review_status="accepted",
            ),
        ],
    )


def test_exclude_jurisdiction_by_title() -> None:
    result = make_law_proposition_extractor_intake_bundle(
        _jurisdiction_bundle(),
        exclude_jurisdictions={"Northern Ireland"},
    )
    bundle = result.bundle

    assert [source.source_id for source in bundle.principal_sources] == ["gb-wide"]
    assert bundle.amending_sources == []
    assert bundle.relationships == []


def test_exclude_jurisdiction_by_nisr_uri() -> None:
    result = make_law_proposition_extractor_intake_bundle(
        _jurisdiction_bundle(),
        exclude_jurisdictions={"Northern Ireland"},
    )
    assert all(source.source_id != "ni-uri" for source in result.bundle.principal_sources)


def test_exclude_jurisdiction_keeps_broad_extent() -> None:
    result = make_law_proposition_extractor_intake_bundle(
        _jurisdiction_bundle(),
        exclude_jurisdictions={"Northern Ireland"},
    )
    assert result.bundle.principal_sources[0].source_id == "gb-wide"
    assert "Northern Ireland" in result.bundle.principal_sources[0].jurisdiction_extent


def _priority_bundle() -> SourceBundle:
    return SourceBundle(
        bundle_id="priority-bundle-id",
        category_id="slurry_manure_agricultural_effluent",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        principal_sources=[
            CandidateSource(
                source_id="revoked-npp",
                title="The Nitrate Pollution Prevention Regulations 2008 (revoked)",
                review_status="accepted",
                temporal_status="revoked",
                confidence="high",
            ),
            CandidateSource(
                source_id="other-current",
                title="Some Other Current Slurry Regulation",
                review_status="accepted",
                temporal_status="current",
                confidence="high",
            ),
            CandidateSource(
                source_id="npp-2015",
                title="The Nitrate Pollution Prevention Regulations 2015",
                review_status="accepted",
                temporal_status="current",
                confidence="high",
            ),
            CandidateSource(
                source_id="wales-2021",
                title="The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
                review_status="accepted",
                temporal_status="current",
                confidence="high",
            ),
            CandidateSource(
                source_id="england-2010",
                title="The Water Resources (Control of Pollution) (Silage, Slurry and Agricultural Fuel Oil) (England) Regulations 2010",
                review_status="accepted",
                temporal_status="current",
                confidence="medium",
            ),
        ],
    )


def test_current_core_priority_before_max_principal_sources() -> None:
    result = make_law_proposition_extractor_intake_bundle(
        _priority_bundle(),
        priority_policy="current_core",
        max_principal_sources=3,
    )
    assert [source.source_id for source in result.bundle.principal_sources] == [
        "npp-2015",
        "wales-2021",
        "england-2010",
    ]


def test_current_core_downranks_revoked_instruments() -> None:
    result = make_law_proposition_extractor_intake_bundle(
        _priority_bundle(),
        priority_policy="current_core",
        max_principal_sources=4,
    )
    kept_ids = {source.source_id for source in result.bundle.principal_sources}
    assert "revoked-npp" not in kept_ids
    assert kept_ids == {"npp-2015", "wales-2021", "england-2010", "other-current"}


def test_make_law_proposition_extractor_intake_bundle_help_includes_new_flags() -> None:
    result = runner.invoke(app, ["make-law-proposition-extractor-intake-bundle", "--help"])
    assert result.exit_code == 0
    assert "exclude-jurisdict" in result.stdout
    assert "priority-policy" in result.stdout
    assert "current_core" in result.stdout
