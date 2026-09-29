from __future__ import annotations

from datetime import UTC, datetime

from law_discovery.models import (
    CandidateSource,
    Confidence,
    DiscoveryRun,
    RecommendedAction,
    ReviewPriority,
    ReviewStatus,
    SourceRegister,
)
from law_discovery.triage_helpers import (
    AI_TRIAGE_LIKELY_ACCEPT,
    AI_TRIAGE_LIKELY_REJECT,
    candidate_has_ai_triage,
    effective_review_priority,
    matches_triage_filter,
)

REVOKED_TITLE_MARKERS = ("(revoked)", "repealed")

OBVIOUS_NOISE_TITLE_MARKERS = (
    "Trunk Road",
    "Temporary Traffic",
    "Improvement Act",
    "Harbour Act",
    "Gas Act",
    "Water Act",
    "Railway",
    "Turnpike",
    "Development Consent Order",
    "Associated British Ports",
    "Court of Protection",
    "Data Protection Act",
    "Education Reform Act",
)

ABP_TITLE_MARKERS = (
    "animal by-products",
    "animal by products",
    "abp",
)


def is_revoked_looking_title(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in REVOKED_TITLE_MARKERS)


def is_obvious_noise_title(title: str) -> bool:
    return any(marker in title for marker in OBVIOUS_NOISE_TITLE_MARKERS)


def ai_triage_review_priority(candidate: CandidateSource) -> str | None:
    priority = effective_review_priority(candidate)
    return priority


def matches_abp_title(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in ABP_TITLE_MARKERS)


def effective_review_status(
    candidate: CandidateSource,
    reviews: dict[str, ReviewStatus],
) -> ReviewStatus:
    return reviews.get(candidate.source_id, candidate.review_status)


def build_source_register_from_reviews(
    run: DiscoveryRun,
    reviews: dict[str, ReviewStatus],
    *,
    created_at: datetime | None = None,
) -> SourceRegister:
    accepted_sources: list[CandidateSource] = []
    rejected_sources: list[CandidateSource] = []
    parked_sources: list[CandidateSource] = []

    for candidate in run.candidate_sources:
        status = effective_review_status(candidate, reviews)
        updated = candidate.model_copy(update={"review_status": status})
        if status == "accepted":
            accepted_sources.append(updated)
        elif status == "rejected":
            rejected_sources.append(updated)
        else:
            parked_sources.append(updated)

    return SourceRegister(
        register_id=f"law-discovery-register-{run.category.category_id}",
        category_id=run.category.category_id,
        created_at=created_at or datetime.now(tz=UTC),
        accepted_sources=accepted_sources,
        rejected_sources=rejected_sources,
        parked_sources=parked_sources,
        metadata={
            "discovery_run_id": run.run_id,
            "viewer_review": True,
            "candidate_count": len(run.candidate_sources),
        },
    )


def count_by_confidence(candidates: list[CandidateSource]) -> dict[Confidence, int]:
    counts: dict[Confidence, int] = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for candidate in candidates:
        counts[candidate.confidence] += 1
    return counts


def count_by_review_status(
    candidates: list[CandidateSource],
    reviews: dict[str, ReviewStatus],
) -> dict[ReviewStatus, int]:
    counts: dict[ReviewStatus, int] = {
        "unreviewed": 0,
        "accepted": 0,
        "parked": 0,
        "rejected": 0,
        "needs_more_research": 0,
    }
    for candidate in candidates:
        status = effective_review_status(candidate, reviews)
        counts[status] += 1
    return counts


def text_matches_query(text: str, query: str) -> bool:
    if not query.strip():
        return True
    return query.strip().lower() in text.lower()


def matched_terms_contain(candidate: CandidateSource, query: str) -> bool:
    if not query.strip():
        return True
    needle = query.strip().lower()
    return any(needle in term.lower() for term in candidate.matched_terms)


def filter_candidates(
    candidates: list[CandidateSource],
    reviews: dict[str, ReviewStatus],
    *,
    text_query: str = "",
    confidence: list[Confidence] | None = None,
    source_types: list[str] | None = None,
    relationships: list[str] | None = None,
    review_statuses: list[ReviewStatus] | None = None,
    matched_terms_query: str = "",
    hide_low_confidence: bool = False,
    hide_revoked_looking: bool = False,
    hide_obvious_noise: bool = False,
    only_abp_titles: bool = False,
    only_ai_triaged: bool | None = None,
    ai_likely_accept: bool = False,
    ai_likely_reject: bool = False,
    ai_review_priority: ReviewPriority | None = None,
    ai_recommended_action: RecommendedAction | None = None,
) -> list[CandidateSource]:
    filtered: list[CandidateSource] = []
    for candidate in candidates:
        if hide_low_confidence and candidate.confidence == "low":
            continue
        if hide_revoked_looking and is_revoked_looking_title(candidate.title):
            continue
        if hide_obvious_noise and is_obvious_noise_title(candidate.title):
            continue
        if only_abp_titles and not matches_abp_title(candidate.title):
            continue
        triaged = candidate_has_ai_triage(candidate)
        if only_ai_triaged is True and not triaged:
            continue
        if only_ai_triaged is False and triaged:
            continue
        priority = effective_review_priority(candidate)
        if ai_likely_accept and priority != AI_TRIAGE_LIKELY_ACCEPT:
            continue
        if ai_likely_reject and priority != AI_TRIAGE_LIKELY_REJECT:
            continue
        if not matches_triage_filter(
            candidate,
            review_priority=ai_review_priority,
            recommended_action=ai_recommended_action,
        ):
            continue
        if confidence and candidate.confidence not in confidence:
            continue
        if source_types and candidate.source_type not in source_types:
            continue
        if relationships and candidate.relationship_to_category not in relationships:
            continue
        status = effective_review_status(candidate, reviews)
        if review_statuses and status not in review_statuses:
            continue
        searchable = f"{candidate.title} {candidate.canonical_uri or ''}"
        if not text_matches_query(searchable, text_query):
            continue
        if not matched_terms_contain(candidate, matched_terms_query):
            continue
        filtered.append(candidate)
    return filtered
