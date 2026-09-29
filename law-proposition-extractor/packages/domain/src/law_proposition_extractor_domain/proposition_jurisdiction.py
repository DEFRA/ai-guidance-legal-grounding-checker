"""Source jurisdiction, instrument extent, and territorial fields on propositions."""

from __future__ import annotations

from typing import Any

from .enums import LegalEffectType
from .territory_normalization import (
    coerce_source_jurisdiction_for_proposition,
    extract_territories_from_text,
    normalize_territory_name,
    split_territory_list,
)

def build_instrument_extent_by_source(propositions: list[Any]) -> dict[str, list[str]]:
    """
    Collect instrument-level extent from extent propositions (or source metadata).

    Only includes territories parsed from explicit extent wording — no guessing.
    """
    by_source: dict[str, list[str]] = {}
    for prop in propositions:
        source_id = str(getattr(prop, "source_record_id", "") or "").strip()
        if not source_id:
            continue
        effect = getattr(prop, "legal_effect_type", None)
        if effect is not LegalEffectType.EXTENT and str(effect) != LegalEffectType.EXTENT.value:
            continue
        extent_vals = list(getattr(prop, "extent", None) or [])
        if not extent_vals:
            text = str(getattr(prop, "proposition_text", "") or "")
            action = str(getattr(prop, "action", "") or "")
            extent_vals = extract_territories_from_text(
                f"{text} {action}",
                context="extent",
            )
        cleaned = [normalize_territory_name(x) or x for x in extent_vals]
        cleaned = [x for x in cleaned if x and x in {
            "England",
            "Wales",
            "Scotland",
            "Northern Ireland",
            "Great Britain",
            "United Kingdom",
            "EU",
            "Member State",
        }]
        if cleaned:
            existing = by_source.get(source_id, [])
            for item in cleaned:
                if item not in existing:
                    existing.append(item)
            by_source[source_id] = existing[:8]
    return by_source


def extent_from_source_metadata(source_metadata: dict | None) -> list[str]:
    if not source_metadata:
        return []
    raw = source_metadata.get("extent") or source_metadata.get("instrument_extent")
    if isinstance(raw, str):
        return split_territory_list(raw)
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            norm = normalize_territory_name(str(item))
            if norm and norm not in out:
                out.append(norm)
        return out[:8]
    return []


def apply_proposition_jurisdiction_fields(
    model: Any,
    *,
    source_jurisdiction: str | None = None,
    instrument_extent: list[str] | None = None,
    source_metadata: dict | None = None,
) -> Any:
    """
    Set source_jurisdiction and optionally inherit instrument extent (when empty).

    Does not overwrite territorial_application from classification.
    """
    coarse = str(getattr(model, "jurisdiction", "") or "")
    explicit = str(getattr(model, "source_jurisdiction", "") or "").strip() or None
    resolved_source = coerce_source_jurisdiction_for_proposition(
        coarse_jurisdiction=coarse,
        explicit_source_jurisdiction=explicit or source_jurisdiction,
        source_metadata=source_metadata,
    )
    if resolved_source:
        model.source_jurisdiction = resolved_source

    effect = getattr(model, "legal_effect_type", None)
    is_extent_prop = effect is LegalEffectType.EXTENT or str(effect) == LegalEffectType.EXTENT.value

    inherited = list(instrument_extent or [])
    if not inherited and source_metadata:
        inherited = extent_from_source_metadata(source_metadata)

    current_extent = list(getattr(model, "extent", None) or [])
    if not current_extent and inherited and not is_extent_prop:
        model.extent = list(inherited[:8])

    # Normalise any populated territory arrays.
    model.territorial_application = _normalise_territory_list(
        list(getattr(model, "territorial_application", None) or [])
    )
    if current_extent or is_extent_prop:
        model.extent = _normalise_territory_list(list(getattr(model, "extent", None) or []))

    return model


def _normalise_territory_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for raw in values:
        norm = normalize_territory_name(str(raw))
        if norm and norm not in out:
            out.append(norm)
    return out[:8]


def enrich_proposition_jurisdiction(model: Any) -> Any:
    """Model validator hook: source_jurisdiction + territory list normalisation."""
    return apply_proposition_jurisdiction_fields(model)
