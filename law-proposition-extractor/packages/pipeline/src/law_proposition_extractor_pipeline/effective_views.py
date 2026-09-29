"""Resolve pipeline_review_decisions into non-mutating effective artifact views."""

from __future__ import annotations

import copy
from typing import Any

from law_proposition_extractor_domain import (
    Proposition,
    PropositionExtractionTrace,
    SourceCategorisationRationale,
    SourceInventoryRow,
    SourceTargetLink,
)
from pydantic import BaseModel

from .pipeline_reviews import categorisation_artifact_id, resolve_current_pipeline_review_decision

_EFFECTIVE_STATUS_GENERATED = "generated"

_MODEL_BY_ARTIFACT_TYPE: dict[str, type[BaseModel]] = {
    "source_categorisation_rationale": SourceCategorisationRationale,
    "source_target_link": SourceTargetLink,
    "proposition_extraction_trace": PropositionExtractionTrace,
    "proposition": Proposition,
    "source_inventory_row": SourceInventoryRow,
}

SUPPORTED_EFFECTIVE_ARTIFACT_TYPES = frozenset(_MODEL_BY_ARTIFACT_TYPE.keys())


def pipeline_review_artifact_id(*, artifact_type: str, artifact_row: dict[str, Any]) -> str:
    if artifact_type == "source_categorisation_rationale":
        return categorisation_artifact_id(artifact_row)
    return str(artifact_row.get("id", "")).strip()


def validate_replacement_merged(
    *,
    artifact_type: str,
    original: dict[str, Any],
    replacement_value: Any,
) -> None:
    """Ensure replacement can be merged into original and still validates as the domain model."""
    if artifact_type not in _MODEL_BY_ARTIFACT_TYPE:
        raise ValueError(f"Unsupported artifact_type for validation: {artifact_type!r}")
    if not isinstance(replacement_value, dict):
        raise ValueError(
            f"replacement_value for {artifact_type} must be a JSON object, "
            + f"got {type(replacement_value).__name__}"
        )
    merged = {**original, **replacement_value}
    model = _MODEL_BY_ARTIFACT_TYPE[artifact_type]
    _ = model.model_validate(merged)


def compute_effective_value(
    *,
    original: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a deep copy of the artifact as consumed downstream (override merges when applicable)."""
    base = copy.deepcopy(original)
    if not decision:
        return base
    d = str(decision.get("decision", "")).strip().lower()
    if d != "overridden":
        return base
    rep = decision.get("replacement_value")
    if rep is None:
        return base
    if isinstance(rep, dict):
        return {**base, **copy.deepcopy(rep)}
    raise ValueError("overridden replacement_value must be an object for structured artifacts")


def resolve_effective_artifact_view(
    *,
    artifact_type: str,
    original_artifact: dict[str, Any],
    pipeline_review_decisions: list[dict[str, Any]],
    applies_to_field: str | None = None,
) -> dict[str, Any]:
    """
    Build a review-aware view without mutating ``original_artifact``.

    ``effective_status`` is ``generated`` when there is no current (non-superseded) decision.
    """
    if artifact_type not in SUPPORTED_EFFECTIVE_ARTIFACT_TYPES:
        raise ValueError(f"Unsupported artifact_type: {artifact_type!r}")

    original_snapshot = copy.deepcopy(original_artifact)
    aid = pipeline_review_artifact_id(artifact_type=artifact_type, artifact_row=original_artifact)
    cur = resolve_current_pipeline_review_decision(
        pipeline_review_decisions,
        artifact_type=artifact_type,
        artifact_id=aid,
        applies_to_field=applies_to_field,
    )
    if not cur:
        return {
            "artifact_type": artifact_type,
            "artifact_id": aid,
            "original_artifact": original_snapshot,
            "current_review_decision": None,
            "effective_status": _EFFECTIVE_STATUS_GENERATED,
            "effective_value": copy.deepcopy(original_snapshot),
            "review_reason": "",
            "reviewer": None,
            "reviewed_at": None,
            "applies_to_field": None,
        }

    decision_key = str(cur.get("decision", "")).strip().lower()

    effective_value = compute_effective_value(original=original_artifact, decision=cur)
    return {
        "artifact_type": artifact_type,
        "artifact_id": aid,
        "original_artifact": original_snapshot,
        "current_review_decision": copy.deepcopy(cur),
        "effective_status": decision_key,
        "effective_value": effective_value,
        "review_reason": str(cur.get("reason", "") or ""),
        "reviewer": cur.get("reviewer"),
        "reviewed_at": str(cur.get("reviewed_at", "") or "") or None,
        "applies_to_field": cur.get("applies_to_field"),
    }


def find_original_artifact_in_bundle(
    bundle: dict[str, Any],
    *,
    artifact_type: str,
    artifact_id: str,
) -> dict[str, Any] | None:
    """Locate generated artifact dict in a bundle by pipeline review id."""
    if artifact_type == "source_categorisation_rationale":
        for row in bundle.get("source_categorisation_rationales") or []:
            if isinstance(row, dict) and categorisation_artifact_id(row) == artifact_id:
                return row
        return None
    if artifact_type == "source_target_link":
        for row in bundle.get("source_target_links") or []:
            if isinstance(row, dict) and str(row.get("id", "")).strip() == artifact_id:
                return row
        return None
    if artifact_type == "proposition_extraction_trace":
        for row in bundle.get("proposition_extraction_traces") or []:
            if isinstance(row, dict) and str(row.get("id", "")).strip() == artifact_id:
                return row
        return None
    if artifact_type == "proposition":
        for row in bundle.get("propositions") or []:
            if isinstance(row, dict) and str(row.get("id", "")).strip() == artifact_id:
                return row
        return None
    if artifact_type == "source_inventory_row":
        inv = bundle.get("source_inventory")
        if not isinstance(inv, dict):
            return None
        for row in inv.get("rows") or []:
            if isinstance(row, dict) and str(row.get("id", "")).strip() == artifact_id:
                return row
        return None
    return None
