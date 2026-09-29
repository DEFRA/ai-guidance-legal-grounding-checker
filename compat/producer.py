"""Canonical producer metadata for new run artifacts."""

from __future__ import annotations

from typing import Any

from .component_aliases import COMPONENT_BY_SLUG


def producer_metadata(slug: str) -> dict[str, Any]:
    """Return explicit producer fields for metrics / MODEL metadata."""
    comp = COMPONENT_BY_SLUG[slug]
    return {
        "producer_component": comp.slug,
        "source_kind": comp.source_kind,
        "component_id": comp.slug,
        "component_display_name": comp.display_name,
    }
