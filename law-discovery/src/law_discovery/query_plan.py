from __future__ import annotations

from typing import Any

from law_discovery.models import CategoryBrief, DiscoveryQuery, QueryType

_SOURCE_TYPE_SUFFIXES = ("regulations", "order", "act")
_EXPANSION_CONFIDENCES = frozenset({"high", "medium"})

_BROAD_SPECIES_TERMS = frozenset(
    {
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
    }
)


def _normalised_exclusions(category: CategoryBrief, expansion: object | None) -> set[str]:
    excluded = {term.strip().casefold() for term in category.exclusions if term.strip()}
    if expansion is None:
        return excluded
    for attr in ("suggested_exclusions", "exclusions"):
        items = getattr(expansion, attr, None)
        if not items:
            continue
        for item in items:
            if isinstance(item, str):
                term = item.strip()
            else:
                term = str(getattr(item, "term", "") or "").strip()
            if term:
                excluded.add(term.casefold())
    return excluded


def _triage_guidance_weak_terms(category: CategoryBrief) -> set[str]:
    guidance = category.metadata.get("triage_guidance")
    if not isinstance(guidance, dict):
        return set()
    raw = guidance.get("weak_terms")
    if not isinstance(raw, list):
        return set()
    return {term.strip().casefold() for term in raw if isinstance(term, str) and term.strip()}


def _is_weak_standalone_synonym(synonym: str, weak_terms: set[str]) -> bool:
    normalised = synonym.strip().casefold()
    if not normalised:
        return True
    if normalised in weak_terms:
        return True
    return len(normalised.split()) == 1 and normalised in _BROAD_SPECIES_TERMS


def _queryable_synonyms(category: CategoryBrief) -> list[str]:
    weak_terms = _triage_guidance_weak_terms(category)
    return [
        synonym
        for synonym in _dedupe_synonyms(category.synonyms)
        if not _is_weak_standalone_synonym(synonym, weak_terms)
    ]


def _dedupe_synonyms(synonyms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for synonym in synonyms:
        term = synonym.strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def _expansion_terms(expansion: object | None) -> list[tuple[str, str]]:
    if expansion is None:
        return []
    suggested_terms = getattr(expansion, "suggested_terms", None)
    if not suggested_terms:
        return []

    terms: list[tuple[str, str]] = []
    for item in suggested_terms:
        term = getattr(item, "term", None)
        confidence = getattr(item, "confidence", None)
        if not term or confidence not in _EXPANSION_CONFIDENCES:
            continue
        normalised = str(term).strip()
        if not normalised:
            continue
        terms.append(
            (
                normalised,
                f"AI expansion ({confidence} confidence): {normalised}",
            )
        )
    return terms


def _add_query(
    queries: list[DiscoveryQuery],
    seen: set[str],
    *,
    query: str,
    query_type: QueryType,
    source_system: str,
    rationale: str,
    excluded: set[str],
) -> None:
    normalised = query.strip()
    if not normalised:
        return
    key = normalised.casefold()
    if key in seen or key in excluded:
        return
    seen.add(key)
    queries.append(
        DiscoveryQuery(
            query=normalised,
            query_type=query_type,
            source_system=source_system,
            rationale=rationale,
        )
    )


def build_query_plan(
    category: CategoryBrief,
    source_system: str = "lex",
    expansion: object | None = None,
) -> list[DiscoveryQuery]:
    """Build a deterministic query plan from a category brief (no AI required)."""
    queries: list[DiscoveryQuery] = []
    seen: set[str] = set()
    excluded = _normalised_exclusions(category, expansion)
    synonyms = _queryable_synonyms(category)

    combined_query = f"{category.label.strip()} {category.description.strip()}".strip()
    _add_query(
        queries,
        seen,
        query=combined_query,
        query_type="combined",
        source_system=source_system,
        rationale="Combined category label and description",
        excluded=excluded,
    )
    _add_query(
        queries,
        seen,
        query=category.label,
        query_type="label",
        source_system=source_system,
        rationale="Category label",
        excluded=excluded,
    )

    for synonym in synonyms:
        _add_query(
            queries,
            seen,
            query=synonym,
            query_type="synonym",
            source_system=source_system,
            rationale=f"Category synonym: {synonym}",
            excluded=excluded,
        )

    for jurisdiction_hint in category.jurisdiction_hints:
        hint = jurisdiction_hint.strip()
        if not hint:
            continue
        query = f"{category.label.strip()} {hint}".strip()
        _add_query(
            queries,
            seen,
            query=query,
            query_type="synonym",
            source_system=source_system,
            rationale=f"Jurisdiction-expanded query: {hint}",
            excluded=excluded,
        )

    for synonym in synonyms[:3]:
        for suffix in _SOURCE_TYPE_SUFFIXES:
            query = f"{synonym} {suffix}".strip()
            _add_query(
                queries,
                seen,
                query=query,
                query_type="synonym",
                source_system=source_system,
                rationale=f"Source-type expanded query ({suffix}): {synonym}",
                excluded=excluded,
            )

    for term, rationale in _expansion_terms(expansion):
        _add_query(
            queries,
            seen,
            query=term,
            query_type="synonym",
            source_system=source_system,
            rationale=rationale,
            excluded=excluded,
        )

    return queries


def query_plan_to_jsonable(query_plan: list[DiscoveryQuery]) -> list[dict[str, Any]]:
    return [query.model_dump() for query in query_plan]
