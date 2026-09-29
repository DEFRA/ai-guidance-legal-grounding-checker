from __future__ import annotations

from datetime import UTC, datetime

from law_discovery.models import (
    CandidateSource,
    CandidateTriageMetadata,
    CategoryBrief,
    DiscoveryQuery,
    DiscoveryRun,
)
from law_discovery.triage_helpers import has_ai_triage_notes
from law_discovery.viewer_helpers import (
    ai_triage_review_priority,
    build_source_register_from_reviews,
    filter_candidates,
    is_obvious_noise_title,
    is_revoked_looking_title,
    matches_abp_title,
)


def test_is_revoked_looking_title_detects_revoked_and_repealed() -> None:
    assert is_revoked_looking_title("Foo Act 2000 (revoked)")
    assert is_revoked_looking_title("Repealed Widget Regulations 1999")
    assert not is_revoked_looking_title("Animal By-Products Regulations 2011")


def test_is_obvious_noise_title_detects_local_and_traffic_acts() -> None:
    assert is_obvious_noise_title("M4 Junction 3 Improvement Act 1991")
    assert is_obvious_noise_title("A1 Trunk Road (Durham) Order 2002")
    assert is_obvious_noise_title("Temporary Traffic Regulation Order 2010")
    assert not is_obvious_noise_title("Animal By-Products (Enforcement) (England) Regulations 2013")


def test_matches_abp_title() -> None:
    assert matches_abp_title("Animal By-Products Regulations 2011")
    assert matches_abp_title("Controls on ABP disposal")
    assert not matches_abp_title("Horse Passports Regulations 2009")


def _minimal_run(*candidates: CandidateSource) -> DiscoveryRun:
    return DiscoveryRun(
        run_id="run-test",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(
            category_id="animal_by_products",
            label="Animal by-products",
            description="Test",
        ),
        query_plan=[DiscoveryQuery(query="abp", query_type="label")],
        candidate_sources=list(candidates),
    )


def test_has_ai_triage_notes_and_priority_from_notes() -> None:
    triaged = CandidateSource(
        source_id="t",
        title="Slurry regs",
        notes=(
            "AI triage rationale: Strong match.\n\n"
            "AI triage review_priority: likely_accept"
        ),
    )
    plain = CandidateSource(source_id="p", title="Other", notes="Deterministic only")

    assert has_ai_triage_notes(triaged)
    assert not has_ai_triage_notes(plain)
    assert ai_triage_review_priority(triaged) == "likely_accept"


def test_filter_candidates_structured_ai_triage_filters() -> None:
    likely_accept = CandidateSource(
        source_id="a",
        title="Slurry",
        ai_triage=CandidateTriageMetadata(
            relevance="high",
            review_priority="likely_accept",
            relationship_to_category="directly_regulates",
            confidence_after_ai="high",
            recommended_action="accept_candidate",
            rationale="Core.",
        ),
    )
    reject_action = CandidateSource(
        source_id="b",
        title="Road Act",
        ai_triage=CandidateTriageMetadata(
            relevance="low",
            review_priority="park_contextual",
            relationship_to_category="unknown",
            confidence_after_ai="low",
            recommended_action="reject_candidate",
            rationale="Noise.",
        ),
    )

    assert [c.source_id for c in filter_candidates(
        [likely_accept, reject_action],
        {},
        ai_review_priority="likely_accept",
    )] == ["a"]
    assert [c.source_id for c in filter_candidates(
        [likely_accept, reject_action],
        {},
        ai_recommended_action="reject_candidate",
    )] == ["b"]


def test_filter_candidates_ai_triage_filters() -> None:
    likely_accept = CandidateSource(
        source_id="a",
        title="Slurry",
        notes="AI triage rationale: x\n\nAI triage review_priority: likely_accept",
    )
    likely_reject = CandidateSource(
        source_id="b",
        title="Road Act",
        notes="AI triage rationale: y\n\nAI triage review_priority: likely_reject",
    )
    untriaged = CandidateSource(source_id="c", title="Other")

    assert [c.source_id for c in filter_candidates(
        [likely_accept, likely_reject, untriaged],
        {},
        ai_likely_accept=True,
    )] == ["a"]
    assert [c.source_id for c in filter_candidates(
        [likely_accept, likely_reject, untriaged],
        {},
        ai_likely_reject=True,
    )] == ["b"]
    assert [c.source_id for c in filter_candidates(
        [likely_accept, likely_reject, untriaged],
        {},
        only_ai_triaged=True,
    )] == ["a", "b"]
    assert [c.source_id for c in filter_candidates(
        [likely_accept, likely_reject, untriaged],
        {},
        only_ai_triaged=False,
    )] == ["c"]


def test_build_source_register_from_reviews_buckets_by_status() -> None:
    accepted = CandidateSource(source_id="a", title="Accepted Act", review_status="unreviewed")
    rejected = CandidateSource(source_id="b", title="Rejected Act", review_status="unreviewed")
    parked = CandidateSource(source_id="c", title="Parked Act", review_status="unreviewed")
    run = _minimal_run(accepted, rejected, parked)

    register = build_source_register_from_reviews(
        run,
        {"a": "accepted", "b": "rejected", "c": "needs_more_research"},
        created_at=datetime(2026, 5, 26, 13, 0, tzinfo=UTC),
    )

    assert register.category_id == "animal_by_products"
    assert [s.source_id for s in register.accepted_sources] == ["a"]
    assert register.accepted_sources[0].review_status == "accepted"
    assert [s.source_id for s in register.rejected_sources] == ["b"]
    assert [s.source_id for s in register.parked_sources] == ["c"]
    assert register.parked_sources[0].review_status == "needs_more_research"
    assert register.metadata["discovery_run_id"] == "run-test"
