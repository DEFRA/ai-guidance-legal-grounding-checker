from __future__ import annotations

import re

from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    Confidence,
    EvidenceSnippet,
    RelationshipToCategory,
    ReviewStatus,
    SourceType,
    TemporalStatus,
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_CONFIDENCE_RANK: dict[Confidence, int] = {
    "high": 4,
    "medium": 3,
    "low": 2,
    "unknown": 1,
}

_REVIEW_STATUS_RANK: dict[ReviewStatus, int] = {
    "accepted": 5,
    "needs_more_research": 4,
    "parked": 3,
    "unreviewed": 2,
    "rejected": 1,
}

_LEGISLATION_SOURCE_TYPES: frozenset[SourceType] = frozenset(
    {
        "act",
        "uksi",
        "ukpga",
        "assimilated_eu_law",
        "retained_eu_law",
    }
)


def _normalise(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip().casefold()
    return normalised or None


def _dedupe_key(candidate: CandidateSource) -> str | None:
    uri = _normalise(candidate.canonical_uri)
    if uri:
        return f"uri:{uri}"
    citation = _normalise(candidate.citation)
    if citation:
        return f"citation:{citation}"
    title = _normalise(candidate.title)
    if title:
        return f"title:{title}"
    return None


def _prefer(first: str | None, second: str | None) -> str | None:
    return first if first else second


def _merge_ordered_unique(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in existing}
    for item in incoming:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _evidence_key(snippet: EvidenceSnippet) -> tuple[str, str, str | None, str | None]:
    return (
        snippet.evidence_type,
        snippet.text,
        snippet.uri,
        snippet.locator,
    )


def _merge_evidence(
    existing: list[EvidenceSnippet],
    incoming: list[EvidenceSnippet],
) -> list[EvidenceSnippet]:
    merged = list(existing)
    seen = {_evidence_key(snippet) for snippet in existing}
    for snippet in incoming:
        key = _evidence_key(snippet)
        if key in seen:
            continue
        seen.add(key)
        merged.append(snippet)
    return merged


def _stronger_confidence(left: Confidence, right: Confidence) -> Confidence:
    return left if _CONFIDENCE_RANK[left] >= _CONFIDENCE_RANK[right] else right


def _stronger_review_status(left: ReviewStatus, right: ReviewStatus) -> ReviewStatus:
    return left if _REVIEW_STATUS_RANK[left] >= _REVIEW_STATUS_RANK[right] else right


def _merge_notes(left: str | None, right: str | None) -> str | None:
    notes = [note.strip() for note in (left, right) if note and note.strip()]
    if not notes:
        return None
    unique: list[str] = []
    seen: set[str] = set()
    for note in notes:
        key = note.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(note)
    return "\n\n".join(unique)


def _merge_candidates(first: CandidateSource, second: CandidateSource) -> CandidateSource:
    relationship = (
        _prefer(first.relationship_to_category, second.relationship_to_category) or "unknown"
    )
    return CandidateSource(
        source_id=first.source_id,
        title=_prefer(first.title, second.title) or "Untitled Lex result",
        citation=_prefer(first.citation, second.citation),
        source_type=_prefer(first.source_type, second.source_type) or "unknown",  # type: ignore[arg-type]
        canonical_uri=_prefer(first.canonical_uri, second.canonical_uri),
        source_system=_prefer(first.source_system, second.source_system) or "unknown",  # type: ignore[arg-type]
        jurisdiction_extent=_merge_ordered_unique(
            first.jurisdiction_extent,
            second.jurisdiction_extent,
        ),
        temporal_status=_prefer(first.temporal_status, second.temporal_status) or "unknown",  # type: ignore[arg-type]
        relationship_to_category=relationship,  # type: ignore[arg-type]
        match_basis=_merge_ordered_unique(first.match_basis, second.match_basis),
        matched_terms=_merge_ordered_unique(first.matched_terms, second.matched_terms),
        evidence=_merge_evidence(first.evidence, second.evidence),
        confidence=_stronger_confidence(first.confidence, second.confidence),
        review_status=_stronger_review_status(first.review_status, second.review_status),
        notes=_merge_notes(first.notes, second.notes),
    )


def deduplicate_candidates(candidates: list[CandidateSource]) -> list[CandidateSource]:
    """Merge duplicate candidates by URI, citation, then title."""
    deduped: list[CandidateSource] = []
    index_by_key: dict[str, int] = {}

    for candidate in candidates:
        key = _dedupe_key(candidate)
        if key is None:
            deduped.append(candidate)
            continue
        if key not in index_by_key:
            index_by_key[key] = len(deduped)
            deduped.append(candidate)
            continue
        existing_index = index_by_key[key]
        deduped[existing_index] = _merge_candidates(deduped[existing_index], candidate)

    return deduped


def _label_terms(category: CategoryBrief) -> list[str]:
    return [
        word
        for word in re.split(r"[^a-z0-9]+", category.label.casefold())
        if word and word not in _STOPWORDS
    ]


def _is_strong_category_term(term: str) -> bool:
    cleaned = term.strip()
    return bool(cleaned) and (" " in cleaned or len(cleaned) >= 5)


def _strong_terms(category: CategoryBrief) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for synonym in category.synonyms:
        cleaned = synonym.strip()
        if not cleaned:
            continue
        normalised = cleaned.casefold()
        if _is_strong_category_term(cleaned) and normalised not in seen:
            seen.add(normalised)
            terms.append(normalised)

    for word in _label_terms(category):
        if _is_strong_category_term(word) and word not in seen:
            seen.add(word)
            terms.append(word)

    return terms


def _weak_terms(category: CategoryBrief) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for synonym in category.synonyms:
        cleaned = synonym.strip()
        if not cleaned or _is_strong_category_term(cleaned):
            continue
        normalised = cleaned.casefold()
        if normalised not in seen:
            seen.add(normalised)
            terms.append(normalised)

    for word in _label_terms(category):
        if not _is_strong_category_term(word) and word not in seen:
            seen.add(word)
            terms.append(word)

    return terms


def _category_synonyms(category: CategoryBrief) -> list[str]:
    return [synonym.strip().casefold() for synonym in category.synonyms if synonym.strip()]


def _text_contains_term(text: str, term: str) -> bool:
    return term.casefold() in text.casefold()


def _count_terms_in_text(text: str, terms: list[str]) -> int:
    normalised = text.casefold()
    return sum(1 for term in terms if term.casefold() in normalised)


def _count_profile_term_hits(text: str, terms: list[str]) -> int:
    return _count_terms_in_text(text, terms)


def _has_profile_strong_title_match(title: str, strong_terms: list[str]) -> bool:
    return _count_terms_in_text(title, strong_terms) > 0


def _profile_noise_title_match(title: str, patterns: list[str]) -> bool:
    return _count_terms_in_text(title, patterns) > 0


def _profile_positive_title_match(title: str, patterns: list[str]) -> bool:
    return _count_terms_in_text(title, patterns) > 0


def _title_has_strong_match(title: str, category: CategoryBrief) -> bool:
    return _count_terms_in_text(title, _strong_terms(category)) > 0


def _evidence_has_synonym_match(candidate: CandidateSource, category: CategoryBrief) -> bool:
    synonyms = _category_synonyms(category)
    if not synonyms:
        return False
    for snippet in candidate.evidence:
        text = snippet.text.casefold()
        if any(synonym in text for synonym in synonyms):
            return True
    return False


def _evidence_has_strong_match(candidate: CandidateSource, category: CategoryBrief) -> bool:
    strong = _strong_terms(category)
    if not strong:
        return False
    return any(
        _count_terms_in_text(snippet.text, strong) > 0 for snippet in candidate.evidence
    )


def _matched_strong_terms(candidate: CandidateSource, category: CategoryBrief) -> list[str]:
    strong = _strong_terms(category)
    hits: list[str] = []
    for term in candidate.matched_terms:
        if _count_terms_in_text(term, strong) > 0:
            hits.append(term)
    return hits


def _matched_weak_only(candidate: CandidateSource, category: CategoryBrief) -> bool:
    if not candidate.matched_terms:
        return False
    strong = _strong_terms(category)
    weak = _weak_terms(category)
    has_strong = any(_count_terms_in_text(term, strong) > 0 for term in candidate.matched_terms)
    if has_strong:
        return False
    return any(_count_terms_in_text(term, weak) > 0 for term in candidate.matched_terms)


def _corroboration_count(candidate: CandidateSource, category: CategoryBrief) -> int:
    count = 0
    if _title_has_strong_match(candidate.title, category):
        count += 1
    if _evidence_has_strong_match(candidate, category):
        count += 1
    count += len(_matched_strong_terms(candidate, category))
    if _evidence_has_synonym_match(candidate, category) and not _evidence_has_strong_match(
        candidate,
        category,
    ):
        count += 1
    return count


def _has_strong_category_signal(candidate: CandidateSource, category: CategoryBrief) -> bool:
    if _title_has_strong_match(candidate.title, category):
        return True
    if _evidence_has_strong_match(candidate, category):
        return True
    return bool(_matched_strong_terms(candidate, category))


def _has_useful_evidence(candidate: CandidateSource) -> bool:
    return bool(candidate.evidence or candidate.match_basis or candidate.matched_terms)


def _temporal_status_from_title(title: str) -> TemporalStatus | None:
    normalised = title.casefold()
    if "revoked" in normalised:
        return "revoked"
    if "repealed" in normalised:
        return "historical"
    return None


def _determine_confidence(candidate: CandidateSource, category: CategoryBrief) -> Confidence:
    if _title_has_strong_match(candidate.title, category):
        return "high"

    corroboration = _corroboration_count(candidate, category)
    if corroboration >= 2:
        return "high"

    if _evidence_has_synonym_match(candidate, category):
        return "medium"

    if _matched_strong_terms(candidate, category):
        return "medium"

    if _matched_weak_only(candidate, category):
        return "low"

    if "lex_search" in candidate.match_basis:
        return "low"

    if _has_useful_evidence(candidate):
        return "low"

    return "unknown"


def _determine_relationship_from_signals(
    candidate: CandidateSource,
    *,
    confidence: Confidence,
    strong_category_signal: bool,
) -> RelationshipToCategory:
    source_type = candidate.source_type
    if (
        confidence == "high"
        and strong_category_signal
        and source_type in _LEGISLATION_SOURCE_TYPES
    ):
        return "directly_regulates"
    if source_type in {"explanatory_note", "explanatory_memorandum"}:
        return "explains"
    if source_type in {"guidance", "form", "register"}:
        return "operationalises"
    return "possibly_relevant"


def _determine_relationship(
    candidate: CandidateSource,
    category: CategoryBrief,
    *,
    confidence: Confidence,
) -> RelationshipToCategory:
    return _determine_relationship_from_signals(
        candidate,
        confidence=confidence,
        strong_category_signal=_has_strong_category_signal(candidate, category),
    )


def _apply_scoring_updates(
    candidate: CandidateSource,
    *,
    confidence: Confidence,
    relationship: RelationshipToCategory,
    temporal_status: TemporalStatus | None,
) -> CandidateSource:
    update: dict[str, Confidence | RelationshipToCategory | TemporalStatus] = {
        "confidence": confidence,
        "relationship_to_category": relationship,
    }
    if temporal_status is not None:
        update["temporal_status"] = temporal_status
    return candidate.model_copy(update=update)


def score_candidate(candidate: CandidateSource, category: CategoryBrief) -> CandidateSource:
    """Score a candidate deterministically without mutating the original."""
    confidence = _determine_confidence(candidate, category)
    relationship = _determine_relationship(candidate, category, confidence=confidence)
    temporal = _temporal_status_from_title(candidate.title)
    return _apply_scoring_updates(
        candidate,
        confidence=confidence,
        relationship=relationship,
        temporal_status=temporal,
    )


def score_candidates(
    candidates: list[CandidateSource],
    category: CategoryBrief,
) -> list[CandidateSource]:
    """Score, deduplicate, and sort candidates deterministically."""
    from law_discovery.category_profiles import get_scoring_profile, score_candidate_with_profile

    profile = get_scoring_profile(category.category_id)
    if profile is not None:
        scored = [
            score_candidate_with_profile(candidate, category, profile) for candidate in candidates
        ]
    else:
        scored = [score_candidate(candidate, category) for candidate in candidates]
    return sorted(
        scored,
        key=lambda candidate: (
            _CONFIDENCE_RANK[candidate.confidence] * -1,
            _REVIEW_STATUS_RANK[candidate.review_status] * -1,
            candidate.title.casefold(),
        ),
    )


# Backwards-compatible alias used by discovery_service.
rank_candidates = score_candidates
