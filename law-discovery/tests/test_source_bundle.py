from __future__ import annotations

from datetime import UTC, datetime

from law_discovery.models import (
    CandidateSource,
    RelatedSourceExpansionRun,
    SourceRegister,
    SourceRelationship,
)
from law_discovery.source_bundle import build_source_bundle


def _register() -> SourceRegister:
    return SourceRegister(
        register_id="reg-1",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        accepted_sources=[
            CandidateSource(
                source_id="principal",
                title="Horse Passports Regulations 2009",
                relationship_to_category="directly_regulates",
                review_status="accepted",
            )
        ],
        parked_sources=[
            CandidateSource(
                source_id="parked",
                title="Parked contextual instrument",
                review_status="parked",
            )
        ],
    )


def test_principal_sources_from_accepted_register() -> None:
    bundle = build_source_bundle("equine_identification", _register())
    assert len(bundle.principal_sources) == 1
    assert bundle.principal_sources[0].source_id == "principal"
    assert len(bundle.contextual_sources) == 1


def test_amendment_relationship_buckets_candidate() -> None:
    related = CandidateSource(
        source_id="amend",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
    )
    related_run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 5, 26, 11, 0, tzinfo=UTC),
        category_id="equine_identification",
        seed_sources=[CandidateSource(source_id="principal", title="Seed")],
        related_sources=[related],
        relationships=[
            SourceRelationship(
                relationship_id="rel:principal:amend:amended_by",
                from_source_id="principal",
                to_source_id="amend",
                relationship_type="amended_by",
                review_status="accepted",
            )
        ],
    )
    bundle = build_source_bundle("equine_identification", _register(), related_run)
    assert any(source.source_id == "amend" for source in bundle.amending_sources)


def test_commencement_correction_guidance_buckets() -> None:
    related_run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 5, 26, 11, 0, tzinfo=UTC),
        category_id="equine_identification",
        seed_sources=[],
        related_sources=[
            CandidateSource(source_id="c1", title="Commencement"),
            CandidateSource(source_id="c2", title="Correction"),
            CandidateSource(source_id="c3", title="Guidance"),
        ],
        relationships=[
            SourceRelationship(
                relationship_id="r1",
                from_source_id="principal",
                to_source_id="c1",
                relationship_type="commenced_by",
                review_status="accepted",
            ),
            SourceRelationship(
                relationship_id="r2",
                from_source_id="principal",
                to_source_id="c2",
                relationship_type="corrected_by",
                review_status="accepted",
            ),
            SourceRelationship(
                relationship_id="r3",
                from_source_id="principal",
                to_source_id="c3",
                relationship_type="guidance_for",
                review_status="accepted",
            ),
        ],
    )
    bundle = build_source_bundle("equine_identification", _register(), related_run)
    assert any(s.source_id == "c1" for s in bundle.commencement_sources)
    assert any(s.source_id == "c2" for s in bundle.correction_sources)
    assert any(s.source_id == "c3" for s in bundle.guidance_sources)


def test_accepted_orphan_related_source_included_in_contextual_bucket() -> None:
    orphan = CandidateSource(
        source_id="orphan",
        title=(
            "The Water Resources (Control of Pollution) (Silage, Slurry and "
            "Agricultural Fuel Oil) (England) Regulations 2010"
        ),
        review_status="accepted",
        relationship_to_category="directly_regulates",
    )
    related_run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 5, 26, 11, 0, tzinfo=UTC),
        category_id="equine_identification",
        seed_sources=[CandidateSource(source_id="principal", title="Seed")],
        related_sources=[orphan],
        relationships=[],
    )
    bundle = build_source_bundle("equine_identification", _register(), related_run)
    assert any(source.source_id == "orphan" for source in bundle.contextual_sources)


def test_deduping_prefers_principal_bucket() -> None:
    duplicate = CandidateSource(
        source_id="dup",
        title="Duplicate in both buckets",
        relationship_to_category="directly_regulates",
        review_status="accepted",
    )
    related_run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 5, 26, 11, 0, tzinfo=UTC),
        category_id="equine_identification",
        seed_sources=[],
        related_sources=[duplicate],
        relationships=[
            SourceRelationship(
                relationship_id="r1",
                from_source_id="principal",
                to_source_id="dup",
                relationship_type="amended_by",
                review_status="accepted",
            )
        ],
    )
    register = _register()
    register.accepted_sources.append(duplicate)
    bundle = build_source_bundle("equine_identification", register, related_run)
    principal_ids = {s.source_id for s in bundle.principal_sources}
    amending_ids = {s.source_id for s in bundle.amending_sources}
    assert "dup" in principal_ids
    assert "dup" not in amending_ids
