import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from law_proposition_extractor_domain import (
    Cluster,
    ReviewDecision,
    ReviewStatus,
    SourceFragment,
    SourceRecord,
    SourceSnapshot,
    Topic,
)
from law_proposition_extractor_pipeline.fragment_types import fragment_type_from_locator


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def create_topic(name: str, description: str = "", subject_tags: list[str] | None = None) -> Topic:
    return Topic(
        id=f"topic-{slugify(name)}",
        name=name,
        description=description,
        subject_tags=subject_tags or [],
    )


def create_cluster(topic: Topic, name: str, description: str = "") -> Cluster:
    return Cluster(
        id=f"cluster-{slugify(topic.id + '-' + name)}",
        topic_id=topic.id,
        name=name,
        description=description,
    )


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def register_sources(
    raw_sources: list[dict[str, Any]],
) -> tuple[list[SourceRecord], list[SourceSnapshot], list[SourceFragment], list[ReviewDecision]]:
    sources: list[SourceRecord] = []
    snapshots: list[SourceSnapshot] = []
    fragments: list[SourceFragment] = []
    reviews: list[ReviewDecision] = []

    for index, raw in enumerate(raw_sources, start=1):
        source_id = raw.get("id") or f"src-{slugify(raw['jurisdiction'])}-{index:03d}"
        source_text = raw.get("text", "")
        source_locator = (
            raw.get("authoritative_locator") or raw.get("fragment_locator") or "document:full"
        )
        source_retrieved_at = raw.get("retrieved_at") or datetime.now(UTC)
        source_as_of_date = raw.get("as_of_date")
        source_provenance = raw.get("provenance", "demo.case_file")
        source_version_id = raw.get("version_id") or "v1"
        source_review_status = raw.get("review_status", ReviewStatus.PROPOSED)
        source_hash = content_hash(source_text)
        snapshot_id = raw.get("snapshot_id") or f"snap-{slugify(source_id)}-{source_version_id}"
        fragment_id = raw.get("fragment_id") or f"frag-{slugify(source_id)}-001"

        source = SourceRecord(
            id=source_id,
            title=raw["title"],
            jurisdiction=raw["jurisdiction"],
            citation=raw["citation"],
            kind=raw["kind"],
            authoritative_text=source_text,
            authoritative_locator=source_locator,
            status=raw.get("status", "working"),
            review_status=source_review_status,
            provenance=source_provenance,
            as_of_date=source_as_of_date,
            retrieved_at=source_retrieved_at,
            content_hash=source_hash,
            version_id=source_version_id,
            current_snapshot_id=snapshot_id,
            source_url=raw.get("source_url"),
            metadata=raw.get("metadata", {}),
        )
        snapshot = SourceSnapshot(
            id=snapshot_id,
            source_record_id=source_id,
            version_id=source_version_id,
            authoritative_text=source_text,
            authoritative_locator=source_locator,
            provenance=source_provenance,
            as_of_date=source_as_of_date,
            retrieved_at=source_retrieved_at,
            content_hash=source_hash,
            metadata=raw.get("metadata", {}),
        )
        fragment = SourceFragment(
            id=fragment_id,
            fragment_id=fragment_id,
            source_record_id=source_id,
            source_snapshot_id=snapshot_id,
            fragment_type=(
                str(raw.get("fragment_type", "")).strip()
                or fragment_type_from_locator(str(raw.get("fragment_locator", source_locator)))
            ),
            locator=raw.get("fragment_locator", source_locator),
            fragment_text=source_text,
            fragment_hash=content_hash(source_text),
            text_hash=content_hash(source_text),
            char_start=raw.get("char_start"),
            char_end=raw.get("char_end"),
            parent_fragment_id=raw.get("parent_fragment_id"),
            order_index=raw.get("order_index"),
            review_status=source_review_status,
            metadata=raw.get("metadata", {}),
        )
        review = ReviewDecision(
            id=raw.get("review_decision_id") or f"review-{slugify(fragment_id)}",
            target_type="source_fragment",
            target_id=fragment_id,
            previous_status=None,
            new_status=source_review_status,
            reviewer=raw.get("reviewed_by", "system:intake"),
            note=raw.get("review_rationale", "Initial intake registration."),
            metadata={
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
            },
        )

        disable_exp = False
        if isinstance(raw.get("metadata"), dict):
            disable_exp = bool(raw["metadata"].get("disable_fragment_expansion"))
        if isinstance(fragment.metadata, dict):
            disable_exp = disable_exp or bool(fragment.metadata.get("disable_fragment_expansion"))

        if disable_exp:
            expanded_frags = [fragment]
        else:
            from law_proposition_extractor_llm.settings import LLMSettings

            from law_proposition_extractor_pipeline.source_fragmentation import (
                expand_monolithic_source_fragment,
                max_fragment_body_chars_for_llm_budget,
                reviews_for_expanded_fragments,
            )

            llm_settings = LLMSettings()
            max_body = max_fragment_body_chars_for_llm_budget(
                max_extract_input_tokens=llm_settings.max_extract_input_tokens
            )
            overlap = min(8192, max(512, llm_settings.max_extract_input_tokens // 40))
            expanded_frags = expand_monolithic_source_fragment(
                fragment,
                max_body_chars=max_body,
                overlap_chars=overlap,
                slugify=slugify,
            )

        sources.append(source)
        snapshots.append(snapshot)
        fragments.extend(expanded_frags)
        if len(expanded_frags) > 1:
            reviews.extend(reviews_for_expanded_fragments(review, expanded_frags, slugify=slugify))
        else:
            reviews.append(review)
    return sources, snapshots, fragments, reviews
