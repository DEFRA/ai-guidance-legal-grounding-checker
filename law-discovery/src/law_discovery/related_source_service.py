from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Literal

from law_discovery.ai import (
    AdaAIConfigurationError,
    RelatedSourceAssessment,
    assess_related_sources_with_ai,
    load_ai_settings,
)
from law_discovery.lex_adapter import LexAdapter, LexAdapterError, normalise_lex_result_to_candidate
from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    RelatedSourceExpansionRun,
    SourceRegister,
    SourceRelationship,
)
from law_discovery.progress import DiscoveryProgressEvent, ProgressCallback, emit_progress
from law_discovery.related_query_plan import (
    ExpansionProfile,
    build_related_source_query_plan,
    is_amendment_instrument,
)
from law_discovery.related_source_review import (
    count_orphan_related_sources,
    count_related_source_review_statuses,
    count_relationship_review_statuses,
    finalize_related_sources,
)
from law_discovery.relationship_classifier import (
    classify_relationship_from_title,
    relationship_confidence_rank,
)
from law_discovery.scoring import deduplicate_candidates

SeedSourceType = Literal["principal", "all-accepted"]

_NETWORK_DISABLED_WARNING = "Network related-source discovery was disabled."
_MAX_SEED_RELATIONSHIPS_PER_CANDIDATE = 3

_NON_PRINCIPAL_SEED_RELATIONSHIPS = frozenset(
    {"amends", "commences", "revokes", "explains", "cites"}
)


def _default_run_id(category_id: str) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"law-discovery-related-{category_id}-{timestamp}"


def _is_principal_seed(source: CandidateSource) -> bool:
    if source.relationship_to_category in _NON_PRINCIPAL_SEED_RELATIONSHIPS:
        return False
    return not is_amendment_instrument(source)


def select_seed_sources(
    source_register: SourceRegister,
    *,
    seed_source_type: SeedSourceType = "principal",
    max_seed_sources: int | None = None,
) -> list[CandidateSource]:
    """Select seed sources for related expansion (accepted, else high-confidence parked)."""
    if source_register.accepted_sources:
        seeds = list(source_register.accepted_sources)
    else:
        seeds = [
            source
            for source in source_register.parked_sources
            if source.confidence == "high"
        ]

    if seed_source_type == "principal":
        seeds = [source for source in seeds if _is_principal_seed(source)]

    if max_seed_sources is not None and max_seed_sources > 0:
        seeds = seeds[:max_seed_sources]

    return seeds


def _relationship_sort_key(relationship: SourceRelationship) -> tuple[int, int]:
    query_bonus = 1 if "query_match" in relationship.basis else 0
    return (relationship_confidence_rank(relationship.confidence), query_bonus)


def _build_relationships(
    seed_sources: list[CandidateSource],
    related_sources: list[CandidateSource],
    candidate_provenance: dict[str, set[str]],
) -> list[SourceRelationship]:
    relationships: list[SourceRelationship] = []
    seen_ids: set[str] = set()

    for candidate in related_sources:
        provenance_seeds = candidate_provenance.get(candidate.source_id, set())
        candidate_relationships: list[SourceRelationship] = []

        for seed in seed_sources:
            relationship = classify_relationship_from_title(seed, candidate)
            if relationship is None:
                continue

            from_query = seed.source_id in provenance_seeds
            if relationship.confidence not in {"medium", "high"} and not from_query:
                continue

            if from_query and "query_match" not in relationship.basis:
                relationship = relationship.model_copy(
                    update={"basis": [*relationship.basis, "query_match"]}
                )
            candidate_relationships.append(relationship)

        candidate_relationships.sort(key=_relationship_sort_key, reverse=True)
        for relationship in candidate_relationships[:_MAX_SEED_RELATIONSHIPS_PER_CANDIDATE]:
            if relationship.relationship_id in seen_ids:
                continue
            seen_ids.add(relationship.relationship_id)
            relationships.append(relationship)

    return relationships


def _count_relationship_types(
    relationships: list[SourceRelationship],
) -> dict[str, int]:
    counts = Counter(relationship.relationship_type for relationship in relationships)
    return dict(sorted(counts.items()))


def _count_confidence(
    relationships: list[SourceRelationship],
) -> dict[str, int]:
    counts = Counter(relationship.confidence for relationship in relationships)
    return {level: counts.get(level, 0) for level in ("high", "medium", "low", "unknown")}


def _apply_ai_assessment(
    relationship: SourceRelationship,
    assessment: RelatedSourceAssessment,
) -> SourceRelationship:
    review_status = relationship.review_status
    if assessment.recommended_review_status != "unreviewed":
        review_status = assessment.recommended_review_status

    confidence = relationship.confidence
    if assessment.confidence != "unknown":
        confidence = assessment.confidence

    basis = list(relationship.basis)
    if "ai_triage" not in basis:
        basis.append("ai_triage")

    notes = relationship.notes
    if assessment.rationale:
        notes = assessment.rationale if notes is None else f"{notes}\n\n{assessment.rationale}"

    relationship_type = relationship.relationship_type
    if assessment.relationship_type != "unknown":
        relationship_type = assessment.relationship_type

    return relationship.model_copy(
        update={
            "relationship_type": relationship_type,
            "confidence": confidence,
            "basis": basis,
            "review_status": review_status,
            "notes": notes,
        }
    )


def _merge_ai_assessments(
    relationships: list[SourceRelationship],
    assessments: list[RelatedSourceAssessment],
) -> list[SourceRelationship]:
    by_pair = {
        (item.from_source_id, item.to_source_id): item for item in assessments
    }
    merged: list[SourceRelationship] = []
    for relationship in relationships:
        assessment = by_pair.get((relationship.from_source_id, relationship.to_source_id))
        if assessment is None:
            merged.append(relationship)
        else:
            merged.append(_apply_ai_assessment(relationship, assessment))
    return merged


class RelatedSourceExpansionService:
    """Expand around accepted register sources to discover related legal materials."""

    def __init__(self, lex_adapter: LexAdapter | None = None) -> None:
        self._lex_adapter = lex_adapter

    def run_related_source_expansion(
        self,
        category: CategoryBrief,
        source_register: SourceRegister,
        run_id: str | None = None,
        limit_per_query: int = 5,
        use_network: bool = True,
        use_ai_triage: bool = False,
        ai_model_name: str | None = None,
        litellm_base_url: str | None = None,
        litellm_api_key: str | None = None,
        ai_triage_batch_size: int = 15,
        expansion_profile: ExpansionProfile = "standard",
        seed_source_type: SeedSourceType = "principal",
        max_seed_sources: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> RelatedSourceExpansionRun:
        seed_sources = select_seed_sources(
            source_register,
            seed_source_type=seed_source_type,
            max_seed_sources=max_seed_sources,
        )
        query_plan = build_related_source_query_plan(
            seed_sources,
            expansion_profile=expansion_profile,
        )
        warnings: list[str] = []
        related_sources: list[CandidateSource] = []
        relationships: list[SourceRelationship] = []
        successful_query_count = 0
        failed_query_count = 0
        ai_triage_success = 0
        ai_triage_failure = 0
        raw_candidate_count = 0
        candidate_provenance: dict[str, set[str]] = {}

        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="build_query_plan",
                message=f"Built {len(query_plan)} related-source queries",
                extra={
                    "query_count": len(query_plan),
                    "seed_source_count": len(seed_sources),
                    "expansion_profile": expansion_profile,
                    "queries": [entry.query.query for entry in query_plan],
                },
            ),
        )

        if not seed_sources:
            warnings.append("No seed sources available for related-source expansion.")

        seed_ids = {source.source_id for source in seed_sources}

        if not use_network:
            warnings.append(_NETWORK_DISABLED_WARNING)
        else:
            adapter = self._lex_adapter or LexAdapter()
            adapter.require_base_url()
            raw_candidates: list[CandidateSource] = []
            total_queries = len(query_plan)
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="lex_search_start",
                    message="Searching Lex for related sources",
                    total=total_queries,
                    extra={"unit": "queries", "secondary_label": "collected"},
                ),
            )
            for index, entry in enumerate(query_plan, start=1):
                query = entry.query
                emit_progress(
                    progress_callback,
                    DiscoveryProgressEvent(
                        stage="lex_search_query",
                        message=query.query,
                        current=index,
                        total=total_queries,
                        extra={"query": query.query},
                    ),
                )
                try:
                    lex_results = adapter.search(query.query, limit=limit_per_query)
                except LexAdapterError as exc:
                    failed_query_count += 1
                    warning = (
                        f"Lex search failed for related query {query.query!r}: {exc}. "
                        "Expansion continued with remaining queries."
                    )
                    warnings.append(warning)
                    emit_progress(
                        progress_callback,
                        DiscoveryProgressEvent(stage="warning", message=warning),
                    )
                    emit_progress(
                        progress_callback,
                        DiscoveryProgressEvent(
                            stage="lex_search_result",
                            message=f"Collected {len(raw_candidates)} raw candidates",
                            current=index,
                            total=total_queries,
                            extra={
                                "raw_count": len(raw_candidates),
                                "deduplicated_count": len(related_sources),
                                "query_results": 0,
                                "query": query.query,
                            },
                        ),
                    )
                    continue

                successful_query_count += 1
                for result in lex_results:
                    candidate = normalise_lex_result_to_candidate(result, category, query)
                    raw_candidates.append(candidate)
                    provenance = candidate_provenance.setdefault(candidate.source_id, set())
                    provenance.add(entry.seed_source_id)

                raw_candidate_count = len(raw_candidates)
                emit_progress(
                    progress_callback,
                    DiscoveryProgressEvent(
                        stage="lex_search_result",
                        message=f"Collected {raw_candidate_count} raw candidates",
                        current=index,
                        total=total_queries,
                        extra={
                            "raw_count": raw_candidate_count,
                            "deduplicated_count": len(
                                deduplicate_candidates(raw_candidates)
                            ),
                            "query_results": len(lex_results),
                            "query": query.query,
                        },
                    ),
                )

            related_sources = deduplicate_candidates(raw_candidates)
            related_sources = [
                source for source in related_sources if source.source_id not in seed_ids
            ]
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="lex_search_complete",
                    message=(
                        f"Collected {raw_candidate_count} raw candidates, "
                        f"{len(related_sources)} related sources after deduplication"
                    ),
                    extra={
                        "raw_candidate_count": raw_candidate_count,
                        "related_source_count": len(related_sources),
                    },
                ),
            )

        relationships = _build_relationships(
            seed_sources,
            related_sources,
            candidate_provenance,
        )

        if use_ai_triage and relationships:
            try:
                load_ai_settings(
                    model_name=ai_model_name,
                    base_url=litellm_base_url,
                    api_key=litellm_api_key,
                )
            except AdaAIConfigurationError as exc:
                msg = f"AI relationship triage requested but configuration is invalid: {exc}"
                raise AdaAIConfigurationError(msg) from exc

            assessments = assess_related_sources_with_ai(
                category,
                seed_sources=seed_sources,
                related_sources=related_sources,
                relationships=relationships,
                model_name=ai_model_name,
                base_url=litellm_base_url,
                api_key=litellm_api_key,
                batch_size=ai_triage_batch_size,
                progress_callback=progress_callback,
            )
            fallback_count = sum(
                1
                for item in assessments
                if item.relevance == "uncertain"
                and "AI relationship triage unavailable" in item.rationale
            )
            if fallback_count == len(assessments) and assessments:
                ai_triage_failure = 1
            elif fallback_count:
                ai_triage_failure = 1
                ai_triage_success = 1
            else:
                ai_triage_success = 1
            relationships = _merge_ai_assessments(relationships, assessments)

        related_sources = finalize_related_sources(related_sources, relationships)

        relationship_type_counts = _count_relationship_types(relationships)
        confidence_counts = _count_confidence(relationships)
        related_source_review_counts = count_related_source_review_statuses(related_sources)
        relationship_review_counts = count_relationship_review_statuses(relationships)
        orphan_related_source_count = count_orphan_related_sources(
            related_sources,
            relationships,
        )

        metadata: dict[str, object] = {
            "query_plan": [
                {
                    **entry.query.model_dump(),
                    "seed_source_id": entry.seed_source_id,
                }
                for entry in query_plan
            ],
            "query_count": len(query_plan),
            "seed_source_count": len(seed_sources),
            "expansion_profile": expansion_profile,
            "seed_source_type": seed_source_type,
            "max_seed_sources": max_seed_sources,
            "raw_candidate_count": raw_candidate_count if use_network else None,
            "related_source_count": len(related_sources),
            "relationship_count": len(relationships),
            "relationship_type_counts": relationship_type_counts,
            "confidence_counts": confidence_counts,
            "related_source_review_counts": related_source_review_counts,
            "relationship_review_counts": relationship_review_counts,
            "orphan_related_source_count": orphan_related_source_count,
            "use_network": use_network,
            "use_ai_triage": use_ai_triage,
            "successful_query_count": successful_query_count if use_network else None,
            "failed_query_count": failed_query_count if use_network else None,
            "partial_results": failed_query_count > 0 if use_network else None,
            "ai_triage_success_count": ai_triage_success if use_ai_triage else None,
            "ai_triage_failure_count": ai_triage_failure if use_ai_triage else None,
        }

        return RelatedSourceExpansionRun(
            run_id=run_id or _default_run_id(category.category_id),
            created_at=datetime.now(tz=UTC),
            category_id=category.category_id,
            seed_sources=seed_sources,
            related_sources=related_sources,
            relationships=relationships,
            warnings=warnings,
            metadata=metadata,
        )
