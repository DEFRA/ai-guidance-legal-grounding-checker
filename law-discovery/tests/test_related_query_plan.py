from __future__ import annotations

from law_discovery.models import CandidateSource
from law_discovery.related_query_plan import (
    build_related_source_queries,
    build_related_source_query_plan,
)


def _seed(
    *,
    source_id: str = "uksi/2009/1741",
    title: str = "Horse Passports Regulations 2009",
    citation: str | None = "SI 2009/1741",
    relationship_to_category: str = "directly_regulates",
    temporal_status: str = "unknown",
) -> CandidateSource:
    return CandidateSource(
        source_id=source_id,
        title=title,
        citation=citation,
        relationship_to_category=relationship_to_category,  # type: ignore[arg-type]
        temporal_status=temporal_status,  # type: ignore[arg-type]
    )


def _amendment_seed() -> CandidateSource:
    return _seed(
        source_id="uksi/2015/999",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
        relationship_to_category="amends",
    )


def test_build_related_source_queries_covers_families_standard() -> None:
    queries = build_related_source_queries(_seed(), expansion_profile="standard")
    joined = " | ".join(item.query.casefold() for item in queries)
    assert "amendment regulations" in joined
    assert "revocation" in joined
    assert "commencement" in joined
    assert "correction slip" in joined
    assert "explanatory" in joined
    assert "guidance" in joined
    assert "form" not in joined
    assert "register" not in joined
    assert "database" not in joined


def test_expansion_profile_query_counts() -> None:
    minimal = build_related_source_queries(_seed(), expansion_profile="minimal")
    standard = build_related_source_queries(_seed(), expansion_profile="standard")
    broad = build_related_source_queries(_seed(), expansion_profile="broad")
    assert len(minimal) < len(standard) < len(broad)


def test_amendment_seed_does_not_generate_amendment_queries_standard() -> None:
    queries = build_related_source_queries(
        _amendment_seed(),
        expansion_profile="standard",
    )
    assert not any(
        item.rationale and "Related-source amendment query" in item.rationale
        for item in queries
    )
    joined = " | ".join(item.query.casefold() for item in queries)
    assert "explanatory" in joined
    assert "revocation" in joined
    assert "guidance" not in joined


def test_amendment_title_skips_amendment_queries() -> None:
    queries = build_related_source_queries(
        _seed(title="Foo (Amendment) Regulations 2015"),
        expansion_profile="standard",
    )
    assert not any(
        item.rationale and "Related-source amendment query" in item.rationale
        for item in queries
    )


def test_revoked_source_skips_revocation_queries() -> None:
    queries = build_related_source_queries(
        _seed(title="Foo Regulations 2010 (revoked)", temporal_status="revoked"),
        expansion_profile="standard",
    )
    assert not any(
        item.rationale and "Related-source revocation query" in item.rationale
        for item in queries
    )


def test_minimal_skips_non_principal_relationship_sources() -> None:
    queries = build_related_source_queries(
        _seed(relationship_to_category="amends"),
        expansion_profile="minimal",
    )
    assert queries == []


def test_build_related_source_query_plan_dedupes_case_insensitively() -> None:
    seeds = [_seed(), _seed()]
    plan = build_related_source_query_plan(seeds)
    keys = [entry.query.query.casefold() for entry in plan]
    assert len(keys) == len(set(keys))


def test_build_related_source_query_plan_stable_ordering() -> None:
    plan_a = build_related_source_query_plan([_seed()])
    plan_b = build_related_source_query_plan([_seed()])
    assert [entry.query.query for entry in plan_a] == [
        entry.query.query for entry in plan_b
    ]
