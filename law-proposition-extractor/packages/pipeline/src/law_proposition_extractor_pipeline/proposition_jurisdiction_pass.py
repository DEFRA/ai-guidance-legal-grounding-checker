"""Post-extraction jurisdiction / territory field enrichment."""

from __future__ import annotations

from typing import Any

from law_proposition_extractor_domain import (
    Proposition,
    apply_proposition_jurisdiction_fields,
    build_instrument_extent_by_source,
)
from law_proposition_extractor_domain.proposition_jurisdiction import extent_from_source_metadata


def _source_metadata(source: Any) -> dict | None:
    if source is None:
        return None
    meta = getattr(source, "metadata", None)
    if isinstance(meta, dict):
        return meta
    return None


def apply_post_extraction_jurisdiction_pass(
    propositions: list[Proposition],
    *,
    source_by_id: dict[str, Any] | None = None,
) -> list[Proposition]:
    """
    After classification: set source_jurisdiction and inherit instrument extent per source.

    Mutates propositions in place.
    """
    sources = source_by_id or {}
    extent_by_source = build_instrument_extent_by_source(propositions)

    for proposition in propositions:
        source_id = str(proposition.source_record_id or "").strip()
        source = sources.get(source_id)
        source_meta = _source_metadata(source)
        instrument_extent = extent_by_source.get(source_id)
        if not instrument_extent and source_meta:
            instrument_extent = extent_from_source_metadata(source_meta) or None

        explicit_source_jur = None
        if source is not None:
            explicit_source_jur = str(getattr(source, "jurisdiction", "") or "")

        apply_proposition_jurisdiction_fields(
            proposition,
            source_jurisdiction=explicit_source_jur,
            instrument_extent=instrument_extent,
            source_metadata=source_meta,
        )
    return propositions
