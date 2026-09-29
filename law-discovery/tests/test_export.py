import json
from datetime import UTC, datetime
from pathlib import Path

from law_discovery.export import (
    export_register_json,
    export_selected_sources_for_judit,
    export_source_bundle_for_judit,
    load_register,
    save_selected_sources_for_judit,
    save_source_bundle_for_judit,
)
from law_discovery.models import (
    CandidateSource,
    EvidenceSnippet,
    SourceBundle,
    SourceRegister,
    SourceRelationship,
    save_source_register,
)


def _sample_register() -> SourceRegister:
    accepted = CandidateSource(
        source_id="uksi/2018/123",
        title="Equine Identification (England) Regulations 2018",
        citation="SI 2018/123",
        source_type="uksi",
        canonical_uri="https://www.legislation.gov.uk/uksi/2018/123",
        source_system="lex",
        relationship_to_category="directly_regulates",
        confidence="high",
        review_status="accepted",
        evidence=[
            EvidenceSnippet(
                evidence_type="title",
                text="Equine Identification (England) Regulations 2018",
                uri="https://www.legislation.gov.uk/uksi/2018/123",
            )
        ],
    )
    rejected = CandidateSource(
        source_id="ukpga/1963/2",
        title="Betting, Gaming and Lotteries Act 1963",
        citation="1963 c.2",
        source_type="act",
        review_status="rejected",
    )
    parked = CandidateSource(
        source_id="uksi/2020/1426",
        title="Equine Identification Amendment Regulations 2020",
        citation="SI 2020/1426",
        source_type="uksi",
        review_status="parked",
    )
    return SourceRegister(
        register_id="reg-001",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 10, 15, tzinfo=UTC),
        accepted_sources=[accepted],
        rejected_sources=[rejected],
        parked_sources=[parked],
    )


def test_load_and_export_register_round_trip(tmp_path: Path) -> None:
    register = _sample_register()
    path = tmp_path / "register.json"
    save_source_register(register, path)
    loaded = load_register(path)
    assert loaded.category_id == "equine_identification"
    assert len(loaded.accepted_sources) == 1


def test_export_selected_sources_includes_accepted_only() -> None:
    register = _sample_register()
    payload = export_selected_sources_for_judit(register)

    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["source_id"] == "uksi/2018/123"
    assert payload["sources"][0]["ada_review_status"] == "accepted"
    exported_ids = {source["source_id"] for source in payload["sources"]}
    assert "ukpga/1963/2" not in exported_ids
    assert "uksi/2020/1426" not in exported_ids


def test_export_omits_parked_and_rejected_sources() -> None:
    register = _sample_register()
    payload = export_selected_sources_for_judit(register)
    titles = {source["title"] for source in payload["sources"]}

    assert "Betting, Gaming and Lotteries Act 1963" not in titles
    assert "Equine Identification Amendment Regulations 2020" not in titles


def test_export_preserves_evidence() -> None:
    register = _sample_register()
    payload = export_selected_sources_for_judit(register)

    evidence = payload["sources"][0]["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["evidence_type"] == "title"
    assert "Equine Identification" in evidence[0]["text"]


def test_export_type_and_version_are_present() -> None:
    register = _sample_register()
    payload = export_selected_sources_for_judit(register)

    assert payload["export_type"] == "ada_selected_sources_for_judit"
    assert payload["export_version"] == "0.1"
    assert payload["category_id"] == "equine_identification"
    assert payload["created_at"] == "2026-05-26T10:15:00Z"


def test_export_register_json_is_valid() -> None:
    register = _sample_register()
    payload = export_register_json(register)
    assert "equine_identification" in payload


def _sample_bundle() -> SourceBundle:
    principal = CandidateSource(
        source_id="uksi/2009/1741",
        title="Horse Passports Regulations 2009",
        review_status="accepted",
    )
    amending = CandidateSource(
        source_id="uksi/2015/1",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
    )
    rejected = CandidateSource(source_id="rej", title="Rejected guidance", review_status="rejected")
    return SourceBundle(
        bundle_id="bundle-001",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        principal_sources=[principal],
        amending_sources=[amending],
        rejected_sources=[rejected],
        relationships=[
            SourceRelationship(
                relationship_id="rel:principal:amend:amended_by",
                from_source_id="uksi/2009/1741",
                to_source_id="uksi/2015/1",
                relationship_type="amended_by",
                confidence="high",
                basis=["title_match"],
                evidence=[EvidenceSnippet(evidence_type="title", text=amending.title)],
                review_status="accepted",
            )
        ],
    )


def test_export_source_bundle_for_judit_includes_buckets_and_relationships() -> None:
    bundle = _sample_bundle()
    payload = export_source_bundle_for_judit(bundle)
    exported = payload["source_bundles"][0]
    assert len(exported["principal_sources"]) == 1
    assert len(exported["amending_sources"]) == 1
    assert "rejected_sources" not in exported
    assert len(exported["relationships"]) == 1
    assert exported["relationships"][0]["review_status"] == "accepted"
    assert payload["export_type"] == "ada_source_bundle_for_judit"


def test_save_source_bundle_for_judit_writes_valid_json(tmp_path: Path) -> None:
    bundle = _sample_bundle()
    out = tmp_path / "bundle-for-law-proposition-extractor.json"
    save_source_bundle_for_judit(bundle, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["export_version"] == "0.1"
    assert payload["source_bundles"][0]["relationships"][0]["basis"] == ["title_match"]


def test_save_selected_sources_for_judit_writes_valid_json(tmp_path: Path) -> None:
    register = _sample_register()
    out = tmp_path / "handoff" / "selected-sources.json"
    save_selected_sources_for_judit(register, out)

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["export_type"] == "ada_selected_sources_for_judit"
    assert len(payload["sources"]) == 1
