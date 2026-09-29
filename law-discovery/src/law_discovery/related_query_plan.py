from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from law_discovery.models import CandidateSource, DiscoveryQuery, QueryType

ExpansionProfile = Literal["minimal", "standard", "broad"]
SeedSourceRole = Literal["principal", "amendment"]

_MAX_QUERY_LENGTH = 240

_SKIP_EXPANSION_RELATIONSHIPS = frozenset(
    {"amends", "commences", "revokes", "explains", "cites"}
)

_QUERY_FAMILIES_BROAD: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "amendment",
        (
            "amendment",
            "amended",
            "amending",
            "amendment regulations",
            "amendment order",
        ),
    ),
    (
        "revocation",
        (
            "revoked",
            "revocation",
            "revocation regulations",
            "revocation order",
        ),
    ),
    (
        "commencement",
        (
            "commencement",
            "appointed day",
            "coming into force",
        ),
    ),
    (
        "correction",
        (
            "correction slip",
            "corrigendum",
            "correction",
        ),
    ),
    (
        "interpretive",
        (
            "explanatory note",
            "explanatory memorandum",
            "impact assessment",
            "transposition note",
        ),
    ),
    (
        "guidance_operational",
        (
            "guidance",
            "form",
            "register",
            "database",
        ),
    ),
)

_QUERY_FAMILIES_STANDARD_PRINCIPAL: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("amendment", ("amendment regulations",)),
    ("revocation", ("revocation",)),
    ("commencement", ("commencement",)),
    ("correction", ("correction slip",)),
    (
        "interpretive",
        (
            "explanatory note",
            "explanatory memorandum",
            "impact assessment",
        ),
    ),
    ("guidance_operational", ("guidance",)),
)

_QUERY_FAMILIES_STANDARD_AMENDMENT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("revocation", ("revocation",)),
    ("correction", ("correction slip",)),
    (
        "interpretive",
        (
            "explanatory note",
            "explanatory memorandum",
        ),
    ),
)

_QUERY_FAMILIES_MINIMAL_PRINCIPAL: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("amendment", ("amendment regulations",)),
    ("revocation", ("revocation",)),
    ("correction", ("correction slip",)),
    (
        "interpretive",
        (
            "explanatory note",
            "explanatory memorandum",
        ),
    ),
)


@dataclass(frozen=True)
class RelatedSourceQueryPlanEntry:
    query: DiscoveryQuery
    seed_source_id: str


def _seed_title(source: CandidateSource) -> str:
    title = source.title.strip()
    if title:
        return title
    if source.citation and source.citation.strip():
        return source.citation.strip()
    if source.canonical_uri and source.canonical_uri.strip():
        return source.canonical_uri.strip()
    return source.source_id


def _title_casefold(source: CandidateSource) -> str:
    return _seed_title(source).casefold()


def is_amendment_instrument(source: CandidateSource) -> bool:
    """Return True when the source title or category role indicates an amendment."""
    if source.relationship_to_category == "amends":
        return True
    title = _title_casefold(source)
    return "(amendment)" in title or "amendment regulations" in title


def is_revoked_source(source: CandidateSource) -> bool:
    title = _title_casefold(source)
    return source.temporal_status == "revoked" or "(revoked)" in title


def seed_source_role(source: CandidateSource) -> SeedSourceRole:
    if is_amendment_instrument(source):
        return "amendment"
    return "principal"


def should_skip_expansion(
    source: CandidateSource,
    *,
    expansion_profile: ExpansionProfile,
) -> bool:
    if expansion_profile != "minimal":
        return False
    return source.relationship_to_category in _SKIP_EXPANSION_RELATIONSHIPS


def _families_for_source(
    source: CandidateSource,
    *,
    expansion_profile: ExpansionProfile,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if expansion_profile == "broad":
        return _QUERY_FAMILIES_BROAD

    role = seed_source_role(source)
    if expansion_profile == "minimal":
        if role == "amendment":
            return ()
        return _QUERY_FAMILIES_MINIMAL_PRINCIPAL

    if role == "amendment":
        return _QUERY_FAMILIES_STANDARD_AMENDMENT
    return _QUERY_FAMILIES_STANDARD_PRINCIPAL


def _families_after_title_filters(
    source: CandidateSource,
    families: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    title = _title_casefold(source)
    filtered: list[tuple[str, tuple[str, ...]]] = []

    skip_amendment = "(amendment)" in title or "amendment regulations" in title
    skip_revocation = is_revoked_source(source)

    for family, suffixes in families:
        if family == "amendment" and skip_amendment:
            continue
        if family == "revocation" and skip_revocation:
            continue
        filtered.append((family, suffixes))

    return tuple(filtered)


def _truncate_query(query: str, *, max_len: int = _MAX_QUERY_LENGTH) -> str:
    normalised = query.strip()
    if len(normalised) <= max_len:
        return normalised
    if " " not in normalised:
        return normalised[:max_len].rstrip()
    words = normalised.split()
    truncated_words: list[str] = []
    for word in words:
        candidate = " ".join([*truncated_words, word])
        if len(candidate) > max_len:
            break
        truncated_words.append(word)
    if truncated_words:
        return " ".join(truncated_words)
    return normalised[:max_len].rstrip()


def _normalise_query_key(query: str) -> str:
    return _truncate_query(query).casefold()


def _add_query(
    queries: list[DiscoveryQuery],
    seen: set[str],
    *,
    query: str,
    query_type: QueryType,
    rationale: str,
) -> None:
    normalised = _truncate_query(query)
    if not normalised:
        return
    key = _normalise_query_key(normalised)
    if key in seen:
        return
    seen.add(key)
    queries.append(
        DiscoveryQuery(
            query=normalised,
            query_type=query_type,
            source_system="lex",
            rationale=rationale,
        )
    )


def build_related_source_queries(
    source: CandidateSource,
    *,
    expansion_profile: ExpansionProfile = "standard",
) -> list[DiscoveryQuery]:
    """Build deterministic Lex queries to find materials related to a seed source."""
    if should_skip_expansion(source, expansion_profile=expansion_profile):
        return []

    title = _seed_title(source)
    queries: list[DiscoveryQuery] = []
    seen: set[str] = set()

    families = _families_for_source(source, expansion_profile=expansion_profile)
    families = _families_after_title_filters(source, families)

    for family, suffixes in families:
        for suffix in suffixes:
            _add_query(
                queries,
                seen,
                query=f"{title} {suffix}",
                query_type="manual",
                rationale=(
                    f"Related-source {family} query for seed {source.source_id!r}: "
                    f"{suffix!r}"
                ),
            )

    return queries


def build_related_source_query_plan(
    seed_sources: list[CandidateSource],
    *,
    expansion_profile: ExpansionProfile = "standard",
) -> list[RelatedSourceQueryPlanEntry]:
    """Build a deterministic related-source query plan across seed sources."""
    plan: list[RelatedSourceQueryPlanEntry] = []
    seen: set[str] = set()
    for source in seed_sources:
        for query in build_related_source_queries(
            source,
            expansion_profile=expansion_profile,
        ):
            key = _normalise_query_key(query.query)
            if key in seen:
                continue
            seen.add(key)
            plan.append(
                RelatedSourceQueryPlanEntry(
                    query=query,
                    seed_source_id=source.source_id,
                )
            )
    return plan
