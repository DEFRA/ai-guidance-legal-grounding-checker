from __future__ import annotations

from collections import Counter

from law_discovery.models import (
    CandidateSource,
    RelationshipToCategory,
    SourceRelationship,
)

_CATEGORY_RELEVANCE_TERMS = (
    "slurry",
    "silage",
    "manure",
    "agricultural effluent",
    "ssafo",
    "nitrate vulnerable zone",
    "nitrate vulnerable zones",
    "nitrates action programme",
    "nutrient action programme",
    "agricultural fuel oil",
    "silage, slurry",
)

_SLURRY_SCOPE_TERMS = (
    "slurry",
    "silage",
    "manure",
    "agricultural effluent",
    "ssafo",
)

_OIL_STORAGE_NOISE_NOTE = (
    "Likely oil-storage-only false positive from agricultural fuel oil overlap."
)
_EU_EXIT_NOISE_NOTE = (
    "Generic EU Exit amendment material; requires legal review before treating as related."
)
_FLOODS_WATER_EU_EXIT_NOTE = (
    "Generic Floods and Water EU Exit material matched only via Nitrates Directive "
    "amendment query; requires legal review before treating as related."
)
_ORPHAN_CATEGORY_RELEVANT_NOTE = (
    "Category-relevant related source with no classified seed relationship; "
    "requires manual review or promotion."
)


def _title_lower(title: str) -> str:
    return title.casefold()


def is_category_relevant_title(title: str) -> bool:
    lower = _title_lower(title)
    return any(term in lower for term in _CATEGORY_RELEVANCE_TERMS)


def is_oil_storage_only_noise(title: str) -> bool:
    lower = _title_lower(title)
    if "oil storage" not in lower:
        return False
    return not any(term in lower for term in _SLURRY_SCOPE_TERMS)


def is_generic_eu_exit_material(title: str) -> bool:
    return "eu exit" in _title_lower(title)


def is_floods_water_eu_exit_material(title: str) -> bool:
    return "floods and water (amendment etc.) (eu exit)" in _title_lower(title)


def _matched_nitrates_directive_queries_only(matched_terms: list[str]) -> bool:
    if not matched_terms:
        return False
    directive_markers = ("91/676/eec", "nitrates directive", "nitrates from agricultural")
    return all(
        any(marker in term.casefold() for marker in directive_markers)
        for term in matched_terms
    )


def relationships_for_candidate(
    candidate_id: str,
    relationships: list[SourceRelationship],
) -> list[SourceRelationship]:
    return [item for item in relationships if item.to_source_id == candidate_id]


def has_accepted_relationship(
    candidate_id: str,
    relationships: list[SourceRelationship],
) -> bool:
    return any(
        item.review_status == "accepted"
        for item in relationships_for_candidate(candidate_id, relationships)
    )


def has_accepted_high_medium_relationship(
    candidate_id: str,
    relationships: list[SourceRelationship],
) -> bool:
    return any(
        item.review_status == "accepted" and item.confidence in {"high", "medium"}
        for item in relationships_for_candidate(candidate_id, relationships)
    )


def infer_relationship_to_category(title: str) -> RelationshipToCategory:
    lower = _title_lower(title)
    if "amendment" in lower or "amending" in lower:
        return "amends"
    if "designation of nitrate vulnerable zones" in lower:
        return "operationalises"
    if is_category_relevant_title(title):
        return "directly_regulates"
    return "unknown"


def _append_note(existing: str | None, addition: str) -> str:
    if existing is None or not existing.strip():
        return addition
    if addition in existing:
        return existing
    return f"{existing}\n\n{addition}"


def derive_related_source_review(
    source: CandidateSource,
    relationships: list[SourceRelationship],
) -> CandidateSource:
    """Derive related-source review metadata from relationship review outcomes."""
    candidate_relationships = relationships_for_candidate(source.source_id, relationships)
    updates: dict[str, object] = {}

    if source.relationship_to_category == "unknown":
        inferred = infer_relationship_to_category(source.title)
        if inferred != "unknown":
            updates["relationship_to_category"] = inferred

    if has_accepted_high_medium_relationship(source.source_id, relationships):
        updates["review_status"] = "accepted"
    elif candidate_relationships and all(
        item.review_status == "needs_more_research" for item in candidate_relationships
    ):
        updates["review_status"] = "needs_more_research"
    elif candidate_relationships and all(
        item.review_status == "rejected" for item in candidate_relationships
    ):
        updates["review_status"] = "rejected"
    elif not candidate_relationships:
        if is_category_relevant_title(source.title):
            updates["review_status"] = "needs_more_research"
            updates["notes"] = _append_note(source.notes, _ORPHAN_CATEGORY_RELEVANT_NOTE)
        else:
            updates["review_status"] = "unreviewed"
    elif any(
        item.review_status in {"needs_more_research", "accepted"}
        for item in candidate_relationships
    ):
        updates["review_status"] = "needs_more_research"
    else:
        updates["review_status"] = "unreviewed"

    if not updates:
        return source
    return source.model_copy(update=updates)


def apply_noise_gate_to_related_source(
    source: CandidateSource,
    relationships: list[SourceRelationship],
) -> CandidateSource:
    """Apply deterministic noise/context rules after relationship classification."""
    title = source.title
    updates: dict[str, object] = {}

    if is_oil_storage_only_noise(title):
        updates["review_status"] = "parked"
        updates["notes"] = _append_note(source.notes, _OIL_STORAGE_NOISE_NOTE)
        if source.relationship_to_category == "unknown":
            updates["relationship_to_category"] = "possibly_relevant"

    elif is_floods_water_eu_exit_material(title) and not has_accepted_relationship(
        source.source_id,
        relationships,
    ):
        if _matched_nitrates_directive_queries_only(source.matched_terms):
            updates["review_status"] = "parked"
            updates["notes"] = _append_note(source.notes, _FLOODS_WATER_EU_EXIT_NOTE)
        elif not has_accepted_relationship(source.source_id, relationships):
            updates["review_status"] = "parked"
            updates["notes"] = _append_note(source.notes, _EU_EXIT_NOISE_NOTE)

    elif is_generic_eu_exit_material(title) and not has_accepted_relationship(
        source.source_id,
        relationships,
    ):
        updates["review_status"] = "parked"
        updates["notes"] = _append_note(source.notes, _EU_EXIT_NOISE_NOTE)
        if source.relationship_to_category == "unknown":
            updates["relationship_to_category"] = "possibly_relevant"

    if not updates:
        return source
    return source.model_copy(update=updates)


def finalize_related_sources(
    related_sources: list[CandidateSource],
    relationships: list[SourceRelationship],
) -> list[CandidateSource]:
    """Derive review metadata and apply deterministic noise gates without dropping sources."""
    finalized: list[CandidateSource] = []
    for source in related_sources:
        derived = derive_related_source_review(source, relationships)
        gated = apply_noise_gate_to_related_source(derived, relationships)
        finalized.append(gated)
    return finalized


def count_related_source_review_statuses(
    related_sources: list[CandidateSource],
) -> dict[str, int]:
    counts = Counter(source.review_status for source in related_sources)
    return {
        status: counts.get(status, 0)
        for status in ("accepted", "needs_more_research", "parked", "rejected", "unreviewed")
    }


def count_orphan_related_sources(
    related_sources: list[CandidateSource],
    relationships: list[SourceRelationship],
) -> int:
    related_ids = {source.source_id for source in related_sources}
    linked_ids = {relationship.to_source_id for relationship in relationships}
    return len(related_ids - linked_ids)


def count_relationship_review_statuses(
    relationships: list[SourceRelationship],
) -> dict[str, int]:
    counts = Counter(relationship.review_status for relationship in relationships)
    return {
        status: counts.get(status, 0)
        for status in ("accepted", "needs_more_research", "parked", "rejected", "unreviewed")
    }
