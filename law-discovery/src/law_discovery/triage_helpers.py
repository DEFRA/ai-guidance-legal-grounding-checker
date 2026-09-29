from __future__ import annotations

from collections import Counter
from typing import cast

from law_discovery.ai import CandidateTriageAssessment
from law_discovery.models import (
    CandidateSource,
    CandidateTriageMetadata,
    Confidence,
    RecommendedAction,
    ReviewPriority,
    ReviewStatus,
)

AI_TRIAGE_MARKER = "AI triage rationale:"
AI_TRIAGE_PRIORITY_PREFIX = "AI triage review_priority:"
AI_TRIAGE_ACTION_PREFIX = "AI triage recommended_action:"

AI_TRIAGE_LIKELY_ACCEPT: ReviewPriority = "likely_accept"
AI_TRIAGE_LIKELY_REJECT: ReviewPriority = "likely_reject"

REVIEW_PRIORITY_SORT_ORDER: dict[ReviewPriority, int] = {
    "likely_accept": 0,
    "needs_human_review": 1,
    "park_contextual": 2,
    "likely_reject": 3,
}

TOP_CANDIDATE_LIMIT = 5
NON_TOP_REVIEW_PRIORITIES: frozenset[ReviewPriority] = frozenset({"likely_reject"})


def normalize_triage_assessment(
    assessment: CandidateTriageAssessment,
) -> CandidateTriageAssessment:
    """Normalize confidence_after_ai to relevance confidence semantics."""
    confidence = assessment.confidence_after_ai
    assessment_confidence = assessment.assessment_confidence
    original_confidence = assessment.confidence_after_ai

    if assessment.relevance == "not_relevant":
        confidence = "low"

    if assessment.relevance == "uncertain" and confidence == "high":
        confidence = "unknown"

    if assessment.recommended_action == "reject_candidate" and confidence == "high":
        confidence = "low"

    if (
        assessment.review_priority == "likely_reject"
        and assessment.recommended_action == "reject_candidate"
        and assessment.relevance != "uncertain"
    ):
        confidence = "low"

    if assessment.review_priority == "likely_reject" and confidence == "high":
        confidence = "low"

    if (
        confidence != original_confidence
        and assessment_confidence is None
        and original_confidence == "high"
        and assessment.review_priority == "likely_reject"
    ):
        assessment_confidence = "high"

    if (
        confidence == assessment.confidence_after_ai
        and assessment_confidence == assessment.assessment_confidence
    ):
        return assessment

    return assessment.model_copy(
        update={
            "confidence_after_ai": confidence,
            "assessment_confidence": assessment_confidence,
        }
    )


def triage_metadata_from_assessment(
    assessment: CandidateTriageAssessment,
) -> CandidateTriageMetadata:
    return CandidateTriageMetadata(
        relevance=assessment.relevance,
        review_priority=assessment.review_priority,
        relationship_to_category=assessment.relationship_to_category,
        confidence_after_ai=assessment.confidence_after_ai,
        recommended_action=assessment.recommended_action,
        rationale=assessment.rationale,
        supporting_signals=list(assessment.supporting_signals),
        false_positive_risks=list(assessment.false_positive_risks),
        evidence_limitations=list(assessment.evidence_limitations),
        assessment_confidence=assessment.assessment_confidence,
    )


def has_structured_ai_triage(candidate: CandidateSource) -> bool:
    return candidate.ai_triage is not None


def has_ai_triage_notes(candidate: CandidateSource) -> bool:
    return AI_TRIAGE_MARKER in (candidate.notes or "")


def candidate_has_ai_triage(candidate: CandidateSource) -> bool:
    return has_structured_ai_triage(candidate) or has_ai_triage_notes(candidate)


def discovery_run_has_ai_triage(candidates: list[CandidateSource]) -> bool:
    return any(has_structured_ai_triage(candidate) for candidate in candidates)


def _review_priority_from_notes(candidate: CandidateSource) -> ReviewPriority | None:
    notes = candidate.notes or ""
    for line in notes.splitlines():
        stripped = line.strip()
        if stripped.startswith(AI_TRIAGE_PRIORITY_PREFIX):
            value = stripped.removeprefix(AI_TRIAGE_PRIORITY_PREFIX).strip()
            if value in REVIEW_PRIORITY_SORT_ORDER:
                return cast(ReviewPriority, value)
    return None


def _recommended_action_from_notes(candidate: CandidateSource) -> RecommendedAction | None:
    notes = candidate.notes or ""
    for line in notes.splitlines():
        stripped = line.strip()
        if stripped.startswith(AI_TRIAGE_ACTION_PREFIX):
            value = stripped.removeprefix(AI_TRIAGE_ACTION_PREFIX).strip()
            if value in {
                "accept_candidate",
                "park",
                "reject_candidate",
                "needs_more_research",
            }:
                return cast(RecommendedAction, value)
    return None


def effective_review_priority(candidate: CandidateSource) -> ReviewPriority | None:
    if candidate.ai_triage is not None:
        return candidate.ai_triage.review_priority
    return _review_priority_from_notes(candidate)


def effective_recommended_action(candidate: CandidateSource) -> RecommendedAction | None:
    if candidate.ai_triage is not None:
        return candidate.ai_triage.recommended_action
    return _recommended_action_from_notes(candidate)


def effective_confidence_after_ai(candidate: CandidateSource) -> Confidence | None:
    if candidate.ai_triage is not None:
        return candidate.ai_triage.confidence_after_ai
    return None


def count_by_review_priority(
    candidates: list[CandidateSource],
) -> dict[ReviewPriority, int]:
    counts: dict[ReviewPriority, int] = {
        "likely_accept": 0,
        "needs_human_review": 0,
        "park_contextual": 0,
        "likely_reject": 0,
    }
    for candidate in candidates:
        priority = effective_review_priority(candidate)
        if priority is not None:
            counts[priority] += 1
    return counts


def count_by_recommended_action(
    candidates: list[CandidateSource],
) -> dict[RecommendedAction, int]:
    counts: dict[RecommendedAction, int] = {
        "accept_candidate": 0,
        "needs_more_research": 0,
        "park": 0,
        "reject_candidate": 0,
    }
    for candidate in candidates:
        action = effective_recommended_action(candidate)
        if action is not None:
            counts[action] += 1
    return counts


def count_ai_adjusted_confidence(candidates: list[CandidateSource]) -> dict[Confidence, int]:
    counts: dict[Confidence, int] = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for candidate in candidates:
        confidence = effective_confidence_after_ai(candidate)
        if confidence is not None:
            counts[confidence] += 1
    return counts


def count_deterministic_confidence(candidates: list[CandidateSource]) -> dict[Confidence, int]:
    return dict(Counter(candidate.confidence for candidate in candidates))


def _top_candidate_sort_key(candidate: CandidateSource) -> tuple[int, str]:
    priority = effective_review_priority(candidate)
    order = REVIEW_PRIORITY_SORT_ORDER.get(priority, 99) if priority is not None else 99
    return (order, candidate.title.lower())


def select_top_candidates(
    candidates: list[CandidateSource],
    *,
    limit: int = TOP_CANDIDATE_LIMIT,
) -> list[CandidateSource]:
    if not discovery_run_has_ai_triage(candidates):
        return sorted(
            candidates,
            key=lambda candidate: (
                {"high": 0, "medium": 1, "low": 2, "unknown": 3}.get(
                    candidate.confidence,
                    4,
                ),
                candidate.title.lower(),
            ),
        )[:limit]

    preferred = [
        candidate
        for candidate in candidates
        if effective_review_priority(candidate) not in NON_TOP_REVIEW_PRIORITIES
    ]
    pool = preferred if preferred else list(candidates)
    return sorted(pool, key=_top_candidate_sort_key)[:limit]


def format_top_candidate_line(candidate: CandidateSource) -> str:
    if candidate_has_ai_triage(candidate):
        triage = candidate.ai_triage
        priority = (
            triage.review_priority
            if triage is not None
            else effective_review_priority(candidate) or "unknown"
        )
        action = (
            triage.recommended_action
            if triage is not None
            else effective_recommended_action(candidate) or "unknown"
        )
        confidence = (
            triage.confidence_after_ai
            if triage is not None
            else effective_confidence_after_ai(candidate) or candidate.confidence
        )
        return (
            f"[{priority}] {action} · {confidence} confidence — {candidate.title}"
        )
    return candidate.title


def ai_register_review_status(candidate: CandidateSource) -> ReviewStatus:
    """Map AI triage to register bucket review_status (requires structured ai_triage)."""
    triage = candidate.ai_triage
    if triage is None:
        msg = "candidate missing structured ai_triage"
        raise ValueError(msg)

    if (
        triage.review_priority == "likely_accept"
        or triage.recommended_action == "accept_candidate"
    ):
        return "accepted"
    if triage.review_priority == "likely_reject":
        return "rejected"
    if triage.recommended_action == "reject_candidate":
        return "rejected"
    if triage.recommended_action == "needs_more_research":
        return "needs_more_research"
    return "parked"


def matches_triage_filter(
    candidate: CandidateSource,
    *,
    review_priority: ReviewPriority | None = None,
    recommended_action: RecommendedAction | None = None,
) -> bool:
    priority_ok = (
        review_priority is None
        or effective_review_priority(candidate) == review_priority
    )
    action_ok = (
        recommended_action is None
        or effective_recommended_action(candidate) == recommended_action
    )
    return priority_ok and action_ok
