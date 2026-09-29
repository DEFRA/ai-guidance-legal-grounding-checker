from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from law_discovery.models import (
    CandidateSource,
    RelatedSourceExpansionRun,
    RelatedSourceRelationshipType,
    SourceBundle,
    SourceRegister,
    SourceRelationship,
)

_PRINCIPAL_RELATIONSHIPS = frozenset(
    {
        "directly_regulates",
        "defines_terms",
        "operationalises",
        "possibly_relevant",
        "unknown",
    }
)

_AMENDING_TYPES = frozenset({"amended_by", "amends"})
_COMMENCEMENT_TYPES = frozenset({"commenced_by", "commences"})
_CORRECTION_TYPES = frozenset({"corrected_by", "corrects"})
_REVOCATION_TYPES = frozenset({"revoked_by", "revokes"})
_INTERPRETIVE_TYPES = frozenset(
    {"explained_by", "explains", "transposes", "transposed_by", "implements", "implemented_by"}
)
_GUIDANCE_TYPES = frozenset({"guidance_for"})
_FORM_TYPES = frozenset({"form_for"})

_BUCKET_ORDER: tuple[str, ...] = (
    "principal",
    "amending",
    "commencement",
    "correction",
    "revocation",
    "interpretive",
    "guidance",
    "form",
    "contextual",
    "rejected",
)


def _default_bundle_id(category_id: str) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"law-discovery-bundle-{category_id}-{timestamp}"


def _bucket_for_relationship(
    relationship_type: RelatedSourceRelationshipType,
    review_status: str,
) -> str:
    if review_status == "rejected":
        return "rejected"
    if relationship_type in _AMENDING_TYPES:
        return "amending"
    if relationship_type in _COMMENCEMENT_TYPES:
        return "commencement"
    if relationship_type in _CORRECTION_TYPES:
        return "correction"
    if relationship_type in _REVOCATION_TYPES:
        return "revocation"
    if relationship_type in _INTERPRETIVE_TYPES:
        return "interpretive"
    if relationship_type in _GUIDANCE_TYPES:
        return "guidance"
    if relationship_type in _FORM_TYPES:
        return "form"
    return "contextual"


def _assign_source(
    buckets: dict[str, list[CandidateSource]],
    seen: dict[str, str],
    *,
    source: CandidateSource,
    bucket: str,
) -> None:
    existing = seen.get(source.source_id)
    if existing is not None:
        existing_rank = _BUCKET_ORDER.index(existing)
        new_rank = _BUCKET_ORDER.index(bucket)
        if new_rank >= existing_rank:
            return
        buckets[existing] = [
            item for item in buckets[existing] if item.source_id != source.source_id
        ]
    seen[source.source_id] = bucket
    buckets[bucket].append(source)


def _bucket_for_accepted_orphan(source: CandidateSource) -> str:
    if source.relationship_to_category == "amends":
        return "amending"
    if source.relationship_to_category in _PRINCIPAL_RELATIONSHIPS:
        return "contextual"
    return "contextual"


def build_source_bundle(
    category_id: str,
    source_register: SourceRegister,
    related_run: RelatedSourceExpansionRun | None = None,
) -> SourceBundle:
    """Build a structured source bundle from a register and optional related expansion."""
    buckets: dict[str, list[CandidateSource]] = {name: [] for name in _BUCKET_ORDER}
    seen: dict[str, str] = {}

    for source in source_register.accepted_sources:
        if source.relationship_to_category in _PRINCIPAL_RELATIONSHIPS:
            _assign_source(buckets, seen, source=source, bucket="principal")

    for source in source_register.parked_sources:
        _assign_source(buckets, seen, source=source, bucket="contextual")

    relationships: list[SourceRelationship] = []
    if related_run is not None:
        relationships = list(related_run.relationships)
        related_by_id = {source.source_id: source for source in related_run.related_sources}

        for relationship in relationships:
            if relationship.review_status == "rejected":
                candidate = related_by_id.get(relationship.to_source_id)
                if candidate is not None:
                    _assign_source(buckets, seen, source=candidate, bucket="rejected")
                continue

            allowed_statuses = {
                "accepted",
                "parked",
                "unreviewed",
                "needs_more_research",
            }
            if relationship.review_status not in allowed_statuses:
                continue

            candidate = related_by_id.get(relationship.to_source_id)
            if candidate is None:
                continue

            bucket = _bucket_for_relationship(
                relationship.relationship_type,
                relationship.review_status,
            )
            _assign_source(buckets, seen, source=candidate, bucket=bucket)

        for source in related_run.related_sources:
            if source.source_id in seen:
                continue
            if source.review_status == "rejected":
                _assign_source(buckets, seen, source=source, bucket="rejected")
                continue
            if source.review_status != "accepted":
                continue

            bucket = _bucket_for_accepted_orphan(source)
            _assign_source(buckets, seen, source=source, bucket=bucket)

    return SourceBundle(
        bundle_id=str(uuid4()),
        category_id=category_id,
        created_at=datetime.now(tz=UTC),
        principal_sources=buckets["principal"],
        amending_sources=buckets["amending"],
        commencement_sources=buckets["commencement"],
        correction_sources=buckets["correction"],
        revocation_sources=buckets["revocation"],
        interpretive_sources=buckets["interpretive"],
        guidance_sources=buckets["guidance"],
        form_sources=buckets["form"],
        contextual_sources=buckets["contextual"],
        rejected_sources=buckets["rejected"],
        relationships=relationships,
        metadata={
            "source_register_id": source_register.register_id,
            "related_run_id": related_run.run_id if related_run else None,
        },
    )
