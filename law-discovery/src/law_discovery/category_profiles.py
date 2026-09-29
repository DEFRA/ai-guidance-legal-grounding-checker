from __future__ import annotations

import re
from dataclasses import dataclass

from law_discovery.models import CandidateSource, CategoryBrief, Confidence, TemporalStatus
from law_discovery.scoring import (
    _apply_scoring_updates,
    _count_profile_term_hits,
    _determine_relationship_from_signals,
    _has_profile_strong_title_match,
    _profile_noise_title_match,
    _profile_positive_title_match,
    _temporal_status_from_title,
)

_SLURRY_CATEGORY_ID = "slurry_manure_agricultural_effluent"
_EQUINE_PASSPORTS_CATEGORY_ID = "equine_passports"

_SLURRY_PROFILE = None  # set after CategoryScoringProfile is defined
_EQUINE_PASSPORTS_PROFILE = None  # set after CategoryScoringProfile is defined

_EQUINE_SPECIES_TERMS = (
    r"equine|equines|equidae|equid|equids|horse|horses|pony|ponies|"
    r"donkey|donkeys|mule|mules|zebra|zebras"
)
_EQUINE_ID_MARKERS = (
    r"passport|passports|identification|microchip|microchipping|transponder|"
    r"register|database|ueln|unique equine lifetime number"
)
_EQUINE_CORE_SOURCES = (
    r"equine identification|horse passport|horse passports|identification of equidae|"
    r"identification of equines|equine animal \(identification\)|2015/262"
)
_EQUINE_AMENDMENT_MARKERS = (
    r"amendment|amending|revocation|revoked|revokes|commencement|commences|"
    r"european union \(withdrawal\)|eu exit|assimilated|retained eu"
)

_RE_EQUINE_PASSPORT = re.compile(r"\b(?:equine|horse)\s+passports?\b", re.I)
_RE_EQUINE_SPECIES_WITH_ID = re.compile(
    rf"\b(?:{_EQUINE_SPECIES_TERMS})\b.{{0,40}}\b(?:{_EQUINE_ID_MARKERS})\b|"
    rf"\b(?:{_EQUINE_ID_MARKERS})\b.{{0,40}}\b(?:{_EQUINE_SPECIES_TERMS})\b",
    re.I,
)
_RE_EQUINE_CORE_AMENDMENT = re.compile(
    rf"\b(?:{_EQUINE_CORE_SOURCES})\b.{{0,80}}\b(?:{_EQUINE_AMENDMENT_MARKERS})\b|"
    rf"\b(?:{_EQUINE_AMENDMENT_MARKERS})\b.{{0,80}}\b(?:{_EQUINE_CORE_SOURCES})\b",
    re.I,
)


@dataclass(frozen=True)
class CategoryScoringProfile:
    category_id: str
    strong_terms: list[str]
    weak_terms: list[str]
    noise_title_patterns: list[str]
    positive_title_patterns: list[str]
    broad_terms: list[str] | None = None
    contextual_title_patterns: list[str] | None = None
    requires_anchor_for_high: bool = False
    notes: str | None = None


_PROFILES: dict[str, CategoryScoringProfile] = {}


def _register_profile(profile: CategoryScoringProfile) -> CategoryScoringProfile:
    _PROFILES[profile.category_id] = profile
    return profile


_SLURRY_PROFILE = _register_profile(
    CategoryScoringProfile(
        category_id=_SLURRY_CATEGORY_ID,
        strong_terms=[
            "slurry",
            "slurries",
            "silage effluent",
            "agricultural effluent",
            "farm effluent",
            "manure",
            "farmyard manure",
            "livestock manure",
            "pig slurry",
            "poultry manure",
            "liquid manure",
            "muck spreading",
            "digestate",
            "organic manure",
            "organic fertiliser",
            "nitrate vulnerable zone",
            "agricultural nitrate",
            "agricultural pollution",
            "agricultural diffuse pollution",
            "silage, slurry and agricultural fuel oil",
        ],
        weak_terms=[
            "structural integrity",
            "freeboard",
            "secondary containment",
            "application rate",
            "application rates",
            "closed period",
            "closed periods",
            "buffer zone",
            "buffer zones",
            "water pollution",
            "controlled waters",
            "groundwater protection",
            "land application",
            "reception pit",
            "reception pits",
        ],
        noise_title_patterns=[
            "trunk road",
            "temporary traffic",
            "railway",
            "tramway",
            "merchant shipping",
            "gas orders",
            "corporation act",
            "improvement act",
            "construction (design and management)",
            "vehicle functional safety",
            "plant health",
            "avian influenza",
            "pensions act",
            "government of wales act",
            "companies",
            "court",
            "road act",
            "turnpike",
        ],
        positive_title_patterns=[
            "silage, slurry and agricultural fuel oil",
            "water resources (control of pollution)",
            "water resources (control of agricultural pollution)",
            "agricultural diffuse pollution",
            "nitrate vulnerable zones",
            "protection of water against agricultural nitrate pollution",
            "action programme for nitrate vulnerable zones",
        ],
        notes="Tuned for slurry/manure/agricultural effluent false-positive reduction.",
    )
)

_EQUINE_PASSPORTS_PROFILE = _register_profile(
    CategoryScoringProfile(
        category_id=_EQUINE_PASSPORTS_CATEGORY_ID,
        strong_terms=[
            "equine passport",
            "equine passports",
            "horse passport",
            "horse passports",
            "equine identification",
            "horse identification",
            "identification of equidae",
            "identification of equines",
            "unique equine lifetime number",
            "ueln",
            "passport issuing organisation",
            "passport issuing organisations",
            "central equine database",
            "central equine databases",
            "equine register",
            "equine registers",
            "equine identification regulations",
            "equine animal (identification)",
            "2015/262",
        ],
        weak_terms=[
            "passport",
            "passports",
            "identification document",
            "identification documents",
            "register",
            "database",
            "keeper",
            "owner",
            "movement",
            "transfer",
            "import",
            "food chain",
            "veterinary medicine",
            "slaughter",
            "electronic identification",
        ],
        broad_terms=[
            "horse",
            "horses",
            "pony",
            "ponies",
            "donkey",
            "donkeys",
            "mule",
            "mules",
            "zebra",
            "zebras",
            "equine",
            "equines",
            "equid",
            "equids",
            "equidae",
        ],
        noise_title_patterns=[
            "coal mines",
            "race-horse duty",
            "race horse duty",
            "malvern improvement",
            "electronic identification and trust services",
            "trust services for electronic transactions",
            "improvement act",
            "betting act",
        ],
        positive_title_patterns=[
            "equine identification",
            "equine animal (identification)",
            "horse passports",
            "identification of equidae",
            "2015/262",
        ],
        contextual_title_patterns=[
            "equine infectious",
            "equine disease",
            "equine welfare",
            "equine movement",
            "equine import",
            "imported equine",
            "equine influenza",
        ],
        requires_anchor_for_high=True,
        notes="Tuned for equine passport/identification false-positive reduction.",
    )
)


def get_scoring_profile(category_id: str) -> CategoryScoringProfile | None:
    return _PROFILES.get(category_id)


def _candidate_text(candidate: CandidateSource) -> str:
    parts = [candidate.title]
    parts.extend(snippet.text for snippet in candidate.evidence)
    return "\n".join(parts)


def _equine_passports_anchor_match(text: str) -> bool:
    if _RE_EQUINE_PASSPORT.search(text):
        return True
    if _RE_EQUINE_SPECIES_WITH_ID.search(text):
        return True
    if _RE_EQUINE_CORE_AMENDMENT.search(text):
        return True
    return False


def passes_category_anchor(candidate: CandidateSource, category_id: str) -> bool:
    profile = get_scoring_profile(category_id)
    if profile is None or not profile.requires_anchor_for_high:
        return True
    return _equine_passports_anchor_match(_candidate_text(candidate))


def _profile_broad_or_weak_only(candidate: CandidateSource, profile: CategoryScoringProfile) -> bool:
    if not candidate.matched_terms:
        return False
    broad = profile.broad_terms or []
    weak = profile.weak_terms
    for term in candidate.matched_terms:
        if _count_profile_term_hits(term, profile.strong_terms) > 0:
            return False
        if _count_profile_term_hits(term, broad) > 0:
            continue
        if _count_profile_term_hits(term, weak) > 0:
            continue
        return False
    return True


def _profile_contextual_title_match(title: str, profile: CategoryScoringProfile) -> bool:
    patterns = profile.contextual_title_patterns or []
    return _count_profile_term_hits(title, patterns) > 0


def _profile_strong_title_match(title: str, profile: CategoryScoringProfile) -> bool:
    return _has_profile_strong_title_match(title, profile.strong_terms)


def _profile_corroboration_count(
    candidate: CandidateSource,
    profile: CategoryScoringProfile,
) -> int:
    title_hits = _count_profile_term_hits(candidate.title, profile.strong_terms)
    matched_hits = sum(
        1
        for term in candidate.matched_terms
        if _count_profile_term_hits(term, profile.strong_terms) > 0
    )
    evidence_hits = sum(
        1
        for snippet in candidate.evidence
        if _count_profile_term_hits(snippet.text, profile.strong_terms) > 0
    )
    weak_matched = sum(
        1
        for term in candidate.matched_terms
        if _count_profile_term_hits(term, profile.weak_terms) > 0
    )
    count = 0
    if title_hits:
        count += 1
    if matched_hits:
        count += matched_hits
    if evidence_hits:
        count += evidence_hits
    if weak_matched and title_hits:
        count += 1
    return count


def _determine_profile_confidence(
    candidate: CandidateSource,
    profile: CategoryScoringProfile,
) -> Confidence:
    title = candidate.title
    text = _candidate_text(candidate)
    anchor = not profile.requires_anchor_for_high or _equine_passports_anchor_match(text)

    if (
        _profile_noise_title_match(title, profile.noise_title_patterns)
        and not _profile_positive_title_match(title, profile.positive_title_patterns)
        and not _profile_strong_title_match(title, profile)
    ):
        return "low"

    if _profile_broad_or_weak_only(candidate, profile) and not anchor:
        return "low"

    if anchor and _profile_positive_title_match(title, profile.positive_title_patterns):
        return "high"

    if anchor and _profile_strong_title_match(title, profile):
        return "high"

    corroboration = _profile_corroboration_count(candidate, profile)
    if anchor and corroboration >= 2:
        return "high"

    strong_matched = any(
        _count_profile_term_hits(term, profile.strong_terms) > 0
        for term in candidate.matched_terms
    )
    if anchor and strong_matched and _count_profile_term_hits(title, profile.strong_terms) > 0:
        return "high"

    if strong_matched and anchor:
        return "medium"

    if _profile_contextual_title_match(title, profile) and not anchor:
        return "medium"

    weak_only = bool(candidate.matched_terms) and all(
        _count_profile_term_hits(term, profile.strong_terms) == 0
        for term in candidate.matched_terms
    )
    if weak_only:
        weak_hits = sum(
            _count_profile_term_hits(term, profile.weak_terms)
            for term in candidate.matched_terms
        )
        broad_hits = sum(
            _count_profile_term_hits(term, profile.broad_terms or [])
            for term in candidate.matched_terms
        )
        if (weak_hits or broad_hits) and not anchor:
            return "low"

    if corroboration == 1 and anchor:
        return "medium"

    if "lex_search" in candidate.match_basis:
        return "low"

    if candidate.evidence or candidate.match_basis or candidate.matched_terms:
        return "low"

    return "unknown"


def score_candidate_with_profile(
    candidate: CandidateSource,
    category: CategoryBrief,
    profile: CategoryScoringProfile,
) -> CandidateSource:
    """Score using category-specific profile rules (deterministic, no review mutation)."""
    del category  # profile carries category tuning; brief retained for API consistency
    confidence = _determine_profile_confidence(candidate, profile)
    text = _candidate_text(candidate)
    anchor = not profile.requires_anchor_for_high or _equine_passports_anchor_match(text)
    strong_title = _profile_strong_title_match(candidate.title, profile)
    positive_title = _profile_positive_title_match(
        candidate.title,
        profile.positive_title_patterns,
    )
    evidence_strong = any(
        _count_profile_term_hits(snippet.text, profile.strong_terms) > 0
        for snippet in candidate.evidence
    )
    strong_signal = anchor and (positive_title or strong_title or evidence_strong)
    contextual = _profile_contextual_title_match(candidate.title, profile)
    if contextual and not anchor and confidence != "high":
        relationship = "possibly_relevant"
    else:
        relationship = _determine_relationship_from_signals(
            candidate,
            confidence=confidence,
            strong_category_signal=strong_signal and confidence == "high",
        )
    temporal: TemporalStatus | None = _temporal_status_from_title(candidate.title)
    return _apply_scoring_updates(
        candidate,
        confidence=confidence,
        relationship=relationship,
        temporal_status=temporal,
    )
