from __future__ import annotations

import logging
import re

from law_discovery.models import (
    CandidateSource,
    Confidence,
    EvidenceSnippet,
    RelatedSourceRelationshipType,
    SourceRelationship,
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

_EU_INDICATORS = frozenset(
    {
        "directive",
        "regulation",
        "eu",
        "eec",
        "ec",
    }
)

_CONFIDENCE_RANK: dict[Confidence, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}

_JURISDICTION_GATED_RELATIONSHIPS = frozenset(
    {"amended_by", "revoked_by", "commenced_by", "corrected_by"}
)

_JURISDICTION_EXPANSIONS: dict[str, frozenset[str]] = {
    "england": frozenset({"england"}),
    "wales": frozenset({"wales"}),
    "scotland": frozenset({"scotland"}),
    "northern_ireland": frozenset({"northern_ireland"}),
    "england_and_wales": frozenset({"england", "wales", "england_and_wales"}),
    "great_britain": frozenset({"england", "wales", "scotland", "great_britain"}),
    "uk": frozenset(
        {
            "england",
            "wales",
            "scotland",
            "northern_ireland",
            "england_and_wales",
            "great_britain",
            "uk",
        }
    ),
}

logger = logging.getLogger(__name__)


def normalise_title_for_relationship(text: str) -> str:
    lowered = text.casefold()
    cleaned = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_title_jurisdiction_signals(title: str) -> set[str]:
    """Extract jurisdiction markers from a legislation title."""
    signals: set[str] = set()
    lowered = title.casefold()

    if re.search(r"\(england\s+and\s+wales\)|\bengland\s+and\s+wales\b", lowered):
        signals.update({"england_and_wales", "england", "wales"})

    if re.search(r"\(northern\s+ireland\)", lowered):
        signals.add("northern_ireland")

    if re.search(r"\(scotland\)", lowered):
        signals.add("scotland")

    if re.search(r"\(england\)", lowered):
        signals.add("england")

    if re.search(r"\(wales\)", lowered):
        signals.add("wales")

    if re.search(r"\bgreat\s+britain\b", lowered):
        signals.add("great_britain")

    if re.search(r"\bunited\s+kingdom\b|\buk\b", lowered):
        signals.add("uk")

    return signals


def _expand_jurisdiction_signals(signals: set[str]) -> set[str]:
    expanded: set[str] = set()
    for signal in signals:
        expanded.update(_JURISDICTION_EXPANSIONS.get(signal, {signal}))
    return expanded


def are_title_jurisdictions_compatible(seed_title: str, candidate_title: str) -> bool:
    """Return whether seed and candidate title jurisdictions can refer to the same regime."""
    seed_signals = extract_title_jurisdiction_signals(seed_title)
    candidate_signals = extract_title_jurisdiction_signals(candidate_title)

    if not seed_signals or not candidate_signals:
        return True

    seed_expanded = _expand_jurisdiction_signals(seed_signals)
    candidate_expanded = _expand_jurisdiction_signals(candidate_signals)
    return bool(seed_expanded & candidate_expanded)


def distinctive_title_terms(title: str) -> list[str]:
    normalised = normalise_title_for_relationship(title)
    terms: list[str] = []
    seen: set[str] = set()
    for token in normalised.split():
        if len(token) < 4 or token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def build_relationship_id(from_source_id: str, to_source_id: str) -> str:
    """Stable relationship identifier for a seed→candidate pair (type-independent)."""
    return f"rel:{from_source_id}:{to_source_id}"


def _seed_title(source: CandidateSource) -> str:
    return source.title.strip() or source.citation or source.source_id


def _has_seed_title_overlap(seed_norm: str, candidate_norm: str) -> bool:
    if seed_norm and seed_norm in candidate_norm:
        return True
    distinctive = distinctive_title_terms(seed_norm)
    if not distinctive:
        return False
    overlap = sum(1 for term in distinctive if term in candidate_norm)
    return overlap >= 2


def _strip_jurisdiction_phrases(title: str) -> str:
    stripped = title
    for pattern in (
        r"\(england\s+and\s+wales\)",
        r"\(northern\s+ireland\)",
        r"\(scotland\)",
        r"\(england\)",
        r"\(wales\)",
        r"\bgreat\s+britain\b",
        r"\bunited\s+kingdom\b",
        r"\buk\b",
    ):
        stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stripped).strip()


def _strong_base_title_match(seed_title: str, candidate_title: str) -> bool:
    seed_signals = extract_title_jurisdiction_signals(seed_title)
    candidate_signals = extract_title_jurisdiction_signals(candidate_title)
    if (
        seed_signals
        and candidate_signals
        and not are_title_jurisdictions_compatible(seed_title, candidate_title)
    ):
        return False

    seed_core = _strip_jurisdiction_phrases(seed_title)
    candidate_core = _strip_jurisdiction_phrases(candidate_title)
    seed_norm = normalise_title_for_relationship(seed_core)
    candidate_norm = normalise_title_for_relationship(candidate_core)

    if seed_norm and seed_norm in candidate_norm:
        return True

    distinctive = distinctive_title_terms(seed_core)
    if not distinctive:
        return False

    return all(term in candidate_norm for term in distinctive[:3])


def _is_eu_derived_seed(seed: CandidateSource) -> bool:
    seed_norm = normalise_title_for_relationship(_seed_title(seed))
    return any(indicator in seed_norm for indicator in _EU_INDICATORS)


def _eu_exit_amends_exact_source(seed_title: str, candidate_title: str) -> bool:
    candidate_norm = normalise_title_for_relationship(candidate_title)
    if "amendment" not in candidate_norm and "amending" not in candidate_norm:
        return False
    return _strong_base_title_match(seed_title, candidate_title)


def _title_match_confidence(
    seed_title: str,
    candidate_title: str,
    *,
    relationship_keyword: str,
) -> Confidence:
    seed_norm = normalise_title_for_relationship(seed_title)
    candidate_norm = normalise_title_for_relationship(candidate_title)
    keyword_norm = normalise_title_for_relationship(relationship_keyword)

    if seed_norm and seed_norm in candidate_norm and keyword_norm in candidate_norm:
        return "high"

    distinctive = distinctive_title_terms(seed_title)
    if (
        distinctive
        and all(term in candidate_norm for term in distinctive[:3])
        and keyword_norm in candidate_norm
    ):
        return "medium"

    if keyword_norm in candidate_norm and _has_seed_title_overlap(seed_norm, candidate_norm):
        return "low"

    return "unknown"


def _detect_relationship_type(
    seed: CandidateSource,
    seed_norm: str,
    candidate_norm: str,
    candidate_title: str,
) -> tuple[RelatedSourceRelationshipType, str] | None:
    if not _has_seed_title_overlap(seed_norm, candidate_norm):
        return None

    if "designation of nitrate vulnerable zones" in candidate_norm:
        if _strong_base_title_match(_seed_title(seed), candidate_title):
            return "implemented_by", "designation of nitrate vulnerable zones"
        return "unknown", "designation of nitrate vulnerable zones"

    if "eu exit" in candidate_norm:
        if _is_eu_derived_seed(seed) and _eu_exit_amends_exact_source(
            _seed_title(seed),
            candidate_title,
        ):
            return "amended_by", "amendment"
        if _is_eu_derived_seed(seed):
            return "unknown", "eu exit"
        return None

    if "explanatory memorandum" in candidate_norm:
        return "explained_by", "explanatory memorandum"
    if "explanatory note" in candidate_norm:
        return "explained_by", "explanatory note"

    if "correction slip" in candidate_norm:
        return "corrected_by", "correction slip"
    if "corrigendum" in candidate_norm:
        return "corrected_by", "corrigendum"

    if "commencement" in candidate_norm:
        return "commenced_by", "commencement"
    if "appointed day" in candidate_norm:
        return "commenced_by", "appointed day"
    if "coming into force" in candidate_norm:
        return "commenced_by", "coming into force"

    if "revocation" in candidate_norm:
        return "revoked_by", "revocation"
    if "revoked" in candidate_norm:
        return "revoked_by", "revoked"

    if "impact assessment" in candidate_norm:
        return "explained_by", "impact assessment"
    if "transposition note" in candidate_norm:
        return "explained_by", "transposition note"

    if "amendment" in candidate_norm or "amending" in candidate_norm:
        if _strong_base_title_match(_seed_title(seed), candidate_title):
            return "amended_by", "amendment"
        return None

    if "guidance" in candidate_norm and _strong_base_title_match(
        _seed_title(seed),
        candidate_title,
    ):
        return "guidance_for", "guidance"

    if "form" in candidate_norm and _strong_base_title_match(
        _seed_title(seed),
        candidate_title,
    ):
        return "form_for", "form"

    return None


def classify_relationship_from_title(
    seed: CandidateSource,
    candidate: CandidateSource,
) -> SourceRelationship | None:
    """Classify a seed→candidate relationship from title text (deterministic)."""
    if seed.source_id == candidate.source_id:
        return None

    seed_title = _seed_title(seed)
    candidate_title = candidate.title.strip()
    if not candidate_title:
        return None

    seed_norm = normalise_title_for_relationship(seed_title)
    candidate_norm = normalise_title_for_relationship(candidate_title)
    detected = _detect_relationship_type(seed, seed_norm, candidate_norm, candidate_title)
    if detected is None:
        return None

    relationship_type, keyword = detected

    if (
        relationship_type in _JURISDICTION_GATED_RELATIONSHIPS
        and not are_title_jurisdictions_compatible(seed_title, candidate_title)
    ):
        logger.debug(
            "Jurisdiction mismatch blocked %s: seed=%r candidate=%r",
            relationship_type,
            seed_title,
            candidate_title,
        )
        return None

    confidence = _title_match_confidence(
        seed_title,
        candidate_title,
        relationship_keyword=keyword,
    )

    return SourceRelationship(
        relationship_id=build_relationship_id(seed.source_id, candidate.source_id),
        from_source_id=seed.source_id,
        to_source_id=candidate.source_id,
        relationship_type=relationship_type,
        confidence=confidence,
        basis=["title_match"],
        evidence=[
            EvidenceSnippet(
                evidence_type="title",
                text=candidate_title,
                uri=candidate.canonical_uri,
            )
        ],
    )


def relationship_confidence_rank(confidence: Confidence) -> int:
    return _CONFIDENCE_RANK[confidence]
