import json
from datetime import UTC, datetime
from typing import Any

from law_proposition_extractor_domain import (
    DivergenceAssessment,
    DivergenceObservation,
    ReviewDecision,
    ReviewStatus,
    SourceFragment,
)

_ALLOWED_REVIEW_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.PROPOSED: {
        ReviewStatus.ACCEPTED,
        ReviewStatus.ACCEPTED_WITH_EDITS,
        ReviewStatus.REJECTED,
        ReviewStatus.NEEDS_MORE_SOURCES,
        ReviewStatus.SUPERSEDED,
    },
    ReviewStatus.NEEDS_MORE_SOURCES: {
        ReviewStatus.PROPOSED,
        ReviewStatus.ACCEPTED,
        ReviewStatus.ACCEPTED_WITH_EDITS,
        ReviewStatus.REJECTED,
        ReviewStatus.SUPERSEDED,
    },
    ReviewStatus.ACCEPTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.ACCEPTED_WITH_EDITS: {ReviewStatus.SUPERSEDED},
    ReviewStatus.REJECTED: {ReviewStatus.PROPOSED, ReviewStatus.SUPERSEDED},
    ReviewStatus.SUPERSEDED: set(),
    # Legacy compatibility transitions.
    ReviewStatus.DRAFT: {
        ReviewStatus.PROPOSED,
        ReviewStatus.IN_REVIEW,
        ReviewStatus.ACCEPTED,
        ReviewStatus.ACCEPTED_WITH_EDITS,
        ReviewStatus.REJECTED,
        ReviewStatus.NEEDS_MORE_SOURCES,
        ReviewStatus.SUPERSEDED,
    },
    ReviewStatus.IN_REVIEW: {
        ReviewStatus.PROPOSED,
        ReviewStatus.ACCEPTED,
        ReviewStatus.ACCEPTED_WITH_EDITS,
        ReviewStatus.REJECTED,
        ReviewStatus.NEEDS_MORE_SOURCES,
    },
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _next_review_decision_id(prefix: str, target_id: str) -> str:
    millis = int(_utc_now().timestamp() * 1000)
    return f"review-{prefix}-{target_id}-{millis}"


def parse_edited_fields_payload(raw_payload: str | None) -> dict[str, Any] | None:
    if raw_payload is None or not raw_payload.strip():
        return None
    parsed = json.loads(raw_payload)
    if not isinstance(parsed, dict):
        raise ValueError("edited fields payload must be a JSON object.")
    return parsed


def can_transition_review_status(
    *,
    previous_status: ReviewStatus | None,
    new_status: ReviewStatus,
) -> bool:
    if previous_status is None:
        return True
    if previous_status == new_status:
        return True
    return new_status in _ALLOWED_REVIEW_TRANSITIONS.get(previous_status, set())


def _build_review_decision(
    *,
    target_type: str,
    target_id: str,
    previous_status: ReviewStatus | None,
    new_status: ReviewStatus,
    reviewer: str,
    note: str,
    edited_fields: dict[str, Any] | None,
) -> ReviewDecision:
    if not can_transition_review_status(previous_status=previous_status, new_status=new_status):
        raise ValueError(
            f"Invalid review transition for {target_type}:{target_id} "
            f"{previous_status!s} -> {new_status!s}."
        )
    if new_status == ReviewStatus.ACCEPTED_WITH_EDITS and not edited_fields:
        raise ValueError("accepted_with_edits requires a non-empty edited_fields payload.")

    return ReviewDecision(
        id=_next_review_decision_id(prefix=target_type, target_id=target_id),
        target_type=target_type,
        target_id=target_id,
        previous_status=previous_status,
        new_status=new_status,
        reviewer=reviewer,
        timestamp=_utc_now(),
        note=note,
        edited_fields=edited_fields,
        metadata={},
    )


def apply_review_to_observation(
    *,
    observation: DivergenceObservation,
    new_status: ReviewStatus,
    reviewer: str,
    note: str,
    edited_fields: dict[str, Any] | None = None,
) -> tuple[DivergenceObservation, ReviewDecision]:
    updated_payload = observation.model_dump(mode="json")
    if edited_fields:
        updated_payload.update(edited_fields)
    updated_payload["review_status"] = new_status
    updated_observation = DivergenceObservation.model_validate(updated_payload)
    decision = _build_review_decision(
        # Keep the legacy target_type so existing exports/consumers continue to work.
        target_type="divergence_assessment",
        target_id=observation.id,
        previous_status=observation.review_status,
        new_status=new_status,
        reviewer=reviewer,
        note=note,
        edited_fields=edited_fields,
    )
    return updated_observation, decision


def apply_review_to_assessment(
    *,
    assessment: DivergenceAssessment,
    new_status: ReviewStatus,
    reviewer: str,
    note: str,
    edited_fields: dict[str, Any] | None = None,
) -> tuple[DivergenceAssessment, ReviewDecision]:
    updated_observation, decision = apply_review_to_observation(
        observation=assessment,
        new_status=new_status,
        reviewer=reviewer,
        note=note,
        edited_fields=edited_fields,
    )
    updated_assessment = DivergenceAssessment.model_validate(
        updated_observation.model_dump(mode="json")
    )
    return updated_assessment, decision


def apply_review_to_source_fragment(
    *,
    fragment: SourceFragment,
    new_status: ReviewStatus,
    reviewer: str,
    note: str,
    edited_fields: dict[str, Any] | None = None,
) -> tuple[SourceFragment, ReviewDecision]:
    updated_payload = fragment.model_dump(mode="json")
    if edited_fields:
        updated_payload.update(edited_fields)
    updated_payload["review_status"] = new_status
    updated_fragment = SourceFragment.model_validate(updated_payload)
    decision = _build_review_decision(
        target_type="source_fragment",
        target_id=fragment.id,
        previous_status=fragment.review_status,
        new_status=new_status,
        reviewer=reviewer,
        note=note,
        edited_fields=edited_fields,
    )
    return updated_fragment, decision
