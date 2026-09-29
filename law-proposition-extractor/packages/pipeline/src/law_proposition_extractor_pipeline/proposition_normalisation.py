"""Metadata for deterministic post-extraction proposition normalisation (recorded on runs)."""

from __future__ import annotations

from typing import Any

from law_proposition_extractor_domain import Proposition, apply_relationship_keys

from .proposition_classification_pass import apply_post_extraction_classification_pass
from .proposition_jurisdiction_pass import apply_post_extraction_jurisdiction_pass
from .proposition_labelling_pass import apply_post_extraction_labelling_pass

PROPOSITION_NORMALISATION_VERSION = "1"

PROPOSITION_NORMALISATION_METADATA: dict[str, object] = {
    "enabled": True,
    "version": PROPOSITION_NORMALISATION_VERSION,
    "passes": [
        "classification",
        "jurisdiction",
        "labelling",
        "relationship_keys",
    ],
}


def normalise_extracted_propositions(
    propositions: list[Proposition],
    *,
    source_by_id: dict[str, Any] | None = None,
) -> list[Proposition]:
    """Apply the same post-extraction passes as production runs (no LLM)."""
    apply_post_extraction_classification_pass(propositions)
    apply_post_extraction_jurisdiction_pass(propositions, source_by_id=source_by_id or {})
    apply_post_extraction_labelling_pass(propositions)
    for prop in propositions:
        apply_relationship_keys(prop)
    return propositions
