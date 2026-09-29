from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from law_discovery.ai import RelatedSourceAssessment
from law_discovery.console import DiscoveryConsole, OutputMode
from law_discovery.models import (
    CandidateSource,
    RelatedSourceExpansionRun,
    SourceRegister,
    SourceRelationship,
    load_related_source_expansion_run,
)
from law_discovery.related_source_review import (
    apply_noise_gate_to_related_source,
    finalize_related_sources,
    is_oil_storage_only_noise,
)
from law_discovery.related_source_service import _apply_ai_assessment
from law_discovery.relationship_classifier import build_relationship_id, classify_relationship_from_title
from law_discovery.source_bundle import build_source_bundle


def test_relationship_id_is_type_independent() -> None:
    seed = CandidateSource(source_id="seed-1", title="Horse Passports Regulations 2009")
    candidate = CandidateSource(
        source_id="candidate-1",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
    )
    relationship = classify_relationship_from_title(seed, candidate)
    assert relationship is not None
    assert relationship.relationship_id == "rel:seed-1:candidate-1"
    assert relationship.relationship_id == build_relationship_id("seed-1", "candidate-1")
    assert not relationship.relationship_id.endswith(":amended_by")


def test_ai_relationship_type_change_preserves_relationship_id() -> None:
    relationship = SourceRelationship(
        relationship_id="rel:seed:candidate",
        from_source_id="seed",
        to_source_id="candidate",
        relationship_type="revoked_by",
        confidence="medium",
        basis=["title_match"],
    )
    assessment = RelatedSourceAssessment(
        from_source_id="seed",
        to_source_id="candidate",
        relationship_type="amended_by",
        confidence="high",
        recommended_review_status="accepted",
        rationale="Amends rather than revokes.",
        relevance="high",
    )
    updated = _apply_ai_assessment(relationship, assessment)
    assert updated.relationship_id == "rel:seed:candidate"
    assert updated.relationship_type == "amended_by"
    assert updated.relationship_id.endswith(":amended_by") is False


def test_oil_storage_candidate_marked_parked_with_note() -> None:
    source = CandidateSource(
        source_id="oil-1",
        title="The Water Environment (Oil Storage) (Scotland) Regulations 2006",
    )
    assert is_oil_storage_only_noise(source.title)
    gated = apply_noise_gate_to_related_source(source, [])
    assert gated.review_status == "parked"
    assert gated.notes is not None
    assert "oil-storage-only false positive" in gated.notes


def test_generic_eu_exit_candidate_without_accepted_relationship_is_parked() -> None:
    source = CandidateSource(
        source_id="eu-exit-1",
        title="The Floods and Water (Amendment etc.) (EU Exit) Regulations 2019",
        matched_terms=[
            "Council Directive of 12 December 1991 concerning the protection of waters "
            "against pollution caused by nitrates from agricultural sources (91/676/EEC) "
            "amendment regulations"
        ],
    )
    finalized = finalize_related_sources([source], [])
    assert finalized[0].review_status == "parked"
    assert finalized[0].notes is not None
    assert "EU Exit" in finalized[0].notes
    assert finalized[0].review_status != "accepted"


def test_accepted_orphan_related_source_included_in_source_bundle() -> None:
    orphan = CandidateSource(
        source_id="orphan-2010",
        title=(
            "The Water Resources (Control of Pollution) (Silage, Slurry and "
            "Agricultural Fuel Oil) (England) Regulations 2010"
        ),
        review_status="accepted",
        relationship_to_category="directly_regulates",
        notes="Manually promoted successor instrument.",
    )
    related_run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        category_id="slurry_manure_agricultural_effluent",
        seed_sources=[CandidateSource(source_id="seed", title="Seed")],
        related_sources=[orphan],
        relationships=[],
    )
    register = SourceRegister(
        register_id="reg-1",
        category_id="slurry_manure_agricultural_effluent",
        created_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        accepted_sources=[
            CandidateSource(
                source_id="seed",
                title="Seed",
                relationship_to_category="directly_regulates",
                review_status="accepted",
            )
        ],
    )
    bundle = build_source_bundle("slurry_manure_agricultural_effluent", register, related_run)
    assert any(source.source_id == "orphan-2010" for source in bundle.contextual_sources)


def test_summary_includes_related_source_review_counts() -> None:
    run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        category_id="slurry_manure_agricultural_effluent",
        seed_sources=[],
        related_sources=[
            CandidateSource(source_id="a", title="Accepted", review_status="accepted"),
            CandidateSource(source_id="b", title="Parked", review_status="parked"),
        ],
        relationships=[],
        metadata={
            "query_count": 1,
            "related_source_review_counts": {
                "accepted": 1,
                "needs_more_research": 0,
                "parked": 1,
                "rejected": 0,
                "unreviewed": 0,
            },
            "relationship_review_counts": {
                "accepted": 2,
                "needs_more_research": 1,
                "parked": 0,
                "rejected": 0,
                "unreviewed": 0,
            },
            "orphan_related_source_count": 2,
        },
    )
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)
    console.show_related_expansion_summary(run, Path("out.json"), use_ai_triage=False)
    output = stderr.getvalue()
    assert "related source review:" in output
    assert "accepted: 1" in output
    assert "parked: 1" in output
    assert "relationship review:" in output
    assert "orphan related sources: 2" in output


def test_legacy_relationship_id_suffixes_still_load(tmp_path: Path) -> None:
    payload = {
        "run_id": "legacy-rel-run",
        "created_at": "2026-06-01T12:00:00Z",
        "category_id": "test_category",
        "seed_sources": [{"source_id": "source-a", "title": "Seed act"}],
        "related_sources": [
            {"source_id": "source-b", "title": "Amendment act"},
            {"source_id": "source-c", "title": "Revoking act"},
        ],
        "relationships": [
            {
                "relationship_id": "rel:source-a:source-b:amended_by",
                "from_source_id": "source-a",
                "to_source_id": "source-b",
                "relationship_type": "amended_by",
            },
            {
                "relationship_id": "rel:source-a:source-c",
                "from_source_id": "source-a",
                "to_source_id": "source-c",
                "relationship_type": "revoked_by",
            },
        ],
    }
    path = tmp_path / "legacy-related-run.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    run = load_related_source_expansion_run(path)

    legacy = next(
        relationship
        for relationship in run.relationships
        if relationship.relationship_id == "rel:source-a:source-b:amended_by"
    )
    modern = next(
        relationship
        for relationship in run.relationships
        if relationship.relationship_id == "rel:source-a:source-c"
    )
    assert legacy.relationship_type == "amended_by"
    assert legacy.relationship_id.endswith(":amended_by")
    assert modern.relationship_type == "revoked_by"
    assert not modern.relationship_id.endswith(":revoked_by")
