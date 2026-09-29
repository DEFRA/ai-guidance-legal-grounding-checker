from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from law_discovery.models import (
    CandidateSource,
    CandidateTriageMetadata,
    CategoryBrief,
    DiscoveryQuery,
    DiscoveryRun,
    EvidenceSnippet,
    RelatedSourceExpansionRun,
    SourceBundle,
    SourceRegister,
    SourceRelationship,
    load_category_brief,
    load_discovery_run,
    load_related_source_expansion_run,
    load_source_bundle,
    load_source_register,
    save_discovery_run,
    save_related_source_expansion_run,
    save_source_bundle,
    save_source_register,
)


def test_example_category_loads_into_category_brief(examples_dir: Path) -> None:
    brief = load_category_brief(examples_dir / "equine-identification.category.json")
    assert brief.category_id == "equine_identification"
    assert brief.label == "Equine identification and traceability"
    assert "horse passport" in brief.synonyms
    assert brief.jurisdiction_hints == ["UK", "Great Britain", "England"]


def test_example_source_register_loads(examples_dir: Path) -> None:
    register = load_source_register(
        examples_dir / "equine-identification.source-register.example.json"
    )
    assert register.category_id == "equine_identification"
    assert len(register.accepted_sources) >= 1


def test_example_discovery_run_loads(examples_dir: Path) -> None:
    run = load_discovery_run(examples_dir / "equine-identification.discovery-run.example.json")
    assert run.category.category_id == "equine_identification"
    assert len(run.query_plan) > 0


def test_discovery_run_round_trips_to_json(tmp_path: Path) -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification and traceability",
        description="Test category",
        synonyms=["horse passport"],
    )
    run = DiscoveryRun(
        run_id="run-001",
        created_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        category=category,
        query_plan=[
            DiscoveryQuery(
                query="horse passport",
                query_type="synonym",
                rationale="Category synonym: horse passport",
            )
        ],
        candidate_sources=[
            CandidateSource(
                source_id="uksi/2009/1741",
                title="Horse Passports Regulations 2009",
                citation="SI 2009/1741",
                source_type="uksi",
                canonical_uri="https://www.legislation.gov.uk/uksi/2009/1741",
                source_system="lex",
                matched_terms=["horse passport"],
                confidence="high",
            )
        ],
        warnings=["Lex search incomplete for Scotland"],
    )
    path = tmp_path / "runs" / "discovery.json"
    save_discovery_run(run, path)
    loaded = load_discovery_run(path)
    assert loaded == run


def test_source_register_round_trips_to_json(tmp_path: Path) -> None:
    source = CandidateSource(
        source_id="uksi/2018/123",
        title="Equine Identification (England) Regulations 2018",
        citation="SI 2018/123",
        source_type="uksi",
        review_status="accepted",
    )
    register = SourceRegister(
        register_id="reg-001",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 11, 0, tzinfo=UTC),
        accepted_sources=[source],
        metadata={"reviewer": "example"},
    )
    path = tmp_path / "registers" / "register.json"
    save_source_register(register, path)
    loaded = load_source_register(path)
    assert loaded == register


def test_invalid_review_status_fails_validation() -> None:
    with pytest.raises(ValidationError):
        CandidateSource.model_validate(
            {
                "source_id": "src-1",
                "title": "Example Act",
                "review_status": "maybe_relevant",
            }
        )


def test_candidate_source_loads_without_ai_triage() -> None:
    source = CandidateSource.model_validate(
        {"source_id": "src-1", "title": "Example Act", "confidence": "high"}
    )
    assert source.ai_triage is None


def test_candidate_source_loads_with_ai_triage() -> None:
    source = CandidateSource.model_validate(
        {
            "source_id": "src-1",
            "title": "Example Act",
            "ai_triage": {
                "relevance": "high",
                "review_priority": "likely_accept",
                "relationship_to_category": "directly_regulates",
                "confidence_after_ai": "high",
                "recommended_action": "accept_candidate",
                "rationale": "Core instrument.",
            },
        }
    )
    assert source.ai_triage is not None
    assert source.ai_triage.review_priority == "likely_accept"
    assert isinstance(source.ai_triage, CandidateTriageMetadata)


def test_empty_list_defaults_do_not_share_mutable_state() -> None:
    first = CategoryBrief(
        category_id="first",
        label="First",
        description="First category",
    )
    second = CategoryBrief(
        category_id="second",
        label="Second",
        description="Second category",
    )
    first.synonyms.append("equine")
    first.metadata["scope"] = "England"
    assert second.synonyms == []
    assert second.metadata == {}

    first_source = CandidateSource(source_id="a", title="A")
    second_source = CandidateSource(source_id="b", title="B")
    first_source.matched_terms.append("horse")
    first_source.evidence.append(
        EvidenceSnippet(
            evidence_type="title",
            text="Horse Passports Regulations 2009",
        )
    )
    assert second_source.matched_terms == []
    assert second_source.evidence == []


def test_source_relationship_validates() -> None:
    relationship = SourceRelationship(
        relationship_id="rel:a:b:amended_by",
        from_source_id="a",
        to_source_id="b",
        relationship_type="amended_by",
        confidence="medium",
        basis=["title_match"],
        evidence=[EvidenceSnippet(evidence_type="title", text="Example amendment")],
    )
    assert relationship.review_status == "unreviewed"


def test_related_source_expansion_run_round_trips(tmp_path: Path) -> None:
    run = RelatedSourceExpansionRun(
        run_id="related-001",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category_id="equine_identification",
        seed_sources=[CandidateSource(source_id="a", title="Seed Act")],
        related_sources=[CandidateSource(source_id="b", title="Amendment Act")],
        relationships=[
            SourceRelationship(
                relationship_id="rel:a:b:amended_by",
                from_source_id="a",
                to_source_id="b",
                relationship_type="amended_by",
            )
        ],
    )
    path = tmp_path / "related.json"
    save_related_source_expansion_run(run, path)
    assert load_related_source_expansion_run(path) == run


def test_source_bundle_round_trips(tmp_path: Path) -> None:
    bundle = SourceBundle(
        bundle_id="bundle-001",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 13, 0, tzinfo=UTC),
        principal_sources=[CandidateSource(source_id="a", title="Principal")],
    )
    path = tmp_path / "bundle.json"
    save_source_bundle(bundle, path)
    assert load_source_bundle(path) == bundle
