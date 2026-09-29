"""Build GRF category + lexicon JSON from wizard fields, with term warnings."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from importlib.resources import files
from typing import Any

from guidance_relevance_filter.narrowing import stem_term

_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SLUG_SEP = re.compile(r"[\s_]+")

GENERIC_TERMS = ("farm", "water", "waste", "environment", "animal")


def _stem_one(term: str) -> str | None:
    stemmed = stem_term(term)
    if isinstance(stemmed, str):
        return stemmed
    return None


GENERIC_STEMS = {s for t in GENERIC_TERMS if (s := _stem_one(t))}


def is_slug(name: str) -> bool:
    return bool(_SLUG.fullmatch(name or ""))


def parse_lexicon_lines(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        term = raw.strip()
        if not term or term.startswith("#"):
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def lexicon_warnings(terms: list[str]) -> list[str]:
    warnings: list[str] = []
    for term in terms:
        stemmed = stem_term(term)
        if stemmed is None:
            warnings.append(f"{term!r} stems to nothing (stopwords only) and will never match")
            continue
        if isinstance(stemmed, tuple) and len(stemmed) >= 3:
            warnings.append(
                f"{term!r} is 3+ tokens after stemming — wordsearch only matches unigrams/bigrams"
            )
            continue
        if isinstance(stemmed, str) and stemmed in GENERIC_STEMS:
            warnings.append(
                f"{term!r} is a generic stem ({stemmed!r}) and will route a huge slice of the corpus"
            )
    return warnings


def category_document(
    *,
    name: str,
    description: str,
    exclusion_criteria: str,
    keep_hints: list[str],
    drop_hints: list[str],
) -> list[dict[str, Any]]:
    cat: dict[str, Any] = {
        "name": name,
        "description": description,
        "exclusion_criteria": exclusion_criteria,
    }
    if keep_hints or drop_hints:
        cat["adjudication_hints"] = {"keep": keep_hints, "drop": drop_hints}
    return [cat]


def lexicon_document(name: str, terms: list[str]) -> dict[str, list[str]]:
    return {name: terms}


def parse_hint_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def normalize_slug(value: str) -> str:
    return _SLUG_SEP.sub("-", (value or "").strip().lower()).strip("-")


def parse_csv_list(text: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").split(","):
        item = normalize_slug(raw)
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def parse_scope_list(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """CSV string or JSON array → de-duplicated slugs. Empty = unconstrained."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        seen: set[str] = set()
        for raw in value:
            for item in parse_csv_list(str(raw)):
                if item not in seen:
                    seen.add(item)
                    items.append(item)
        return items
    return parse_csv_list(value)


def title_from_slug(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug or "").strip().title()


def unique_scope(pages: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Unique publisher slugs and document types on a snapshot (case-insensitive sort)."""
    orgs: set[str] = set()
    types: set[str] = set()
    for page in pages:
        md = page.get("meta_data") or {}
        primary = str(md.get("primary_publishing_organisation") or "").strip()
        if primary:
            orgs.add(primary)
        for raw in md.get("organisations") or []:
            slug = str(raw).strip()
            if slug:
                orgs.add(slug)
        document_type = str(md.get("document_type") or "").strip()
        if document_type:
            types.add(document_type)
    return sorted(orgs, key=str.lower), sorted(types, key=str.lower)


# Overlay only — membership comes from unique_scope / MANIFEST.
# Content-store types Discovery pulls as guidance, plus html_publication chapters
# that Stage 2 expands (the Search API dial omits that type).
DOCUMENT_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("guidance", "Guidance"),
    ("detailed_guide", "Detailed guide"),
    ("html_publication", "HTML publication"),
    ("statutory_guidance", "Statutory guidance"),
    ("guide", "Guide"),
    ("manual", "Manual"),
    ("manual_section", "Manual section"),
    ("document_collection", "Document collection"),
    ("data_ethics_guidance_document", "Data ethics guidance document"),
    ("service_manual_topic", "Service manual topic"),
    ("countryside_stewardship_grant", "Countryside stewardship grant"),
    ("service_standard_report", "Service standard report"),
    ("farming_grant", "Farming grant"),
)


def _org(slug: str, label: str, *aliases: str) -> tuple[str, str, tuple[str, ...]]:
    return (slug, label, aliases)


# Label/alias overlay keyed by GOV.UK slug. Aliases are search-only
# (type `defra` to find the department); posted values are slugs.
ORGANISATION_OPTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    _org("advisory-committee-on-business-appointments", "Advisory Committee on Business Appointments", "acoba"),
    _org("animal-and-plant-health-agency", "Animal and Plant Health Agency", "apha"),
    _org("animal-health-and-veterinary-laboratories-agency", "Animal Health and Veterinary Laboratories Agency", "ahvla"),
    _org("british-cattle-movement-service", "British Cattle Movement Service", "bcms"),
    _org("central-digital-and-data-office", "Central Digital and Data Office", "cddo"),
    _org(
        "centre-for-environment-fisheries-and-aquaculture-science",
        "Centre for Environment, Fisheries and Aquaculture Science",
        "cefas",
    ),
    _org("civil-service-government-veterinary-services", "Civil Service Government Veterinary Services"),
    _org("commission-for-rural-communities", "Commission for Rural Communities"),
    _org("consumer-council-for-water", "Consumer Council for Water"),
    _org(
        "department-for-business-energy-and-industrial-strategy",
        "Department for Business, Energy & Industrial Strategy",
        "beis",
    ),
    _org(
        "department-for-energy-security-and-net-zero",
        "Department for Energy Security and Net Zero",
        "desnz",
    ),
    _org(
        "department-for-environment-food-rural-affairs",
        "Department for Environment, Food & Rural Affairs",
        "defra",
    ),
    _org(
        "department-for-levelling-up-housing-and-communities",
        "Department for Levelling Up, Housing and Communities",
        "dluhc",
    ),
    _org("department-for-transport", "Department for Transport", "dft"),
    _org("department-of-energy-climate-change", "Department of Energy and Climate Change", "decc"),
    _org("environment-agency", "Environment Agency", "ea"),
    _org(
        "flood-and-coastal-erosion-risk-management-research-and-development-programme",
        "Flood and Coastal Erosion Risk Management Research and Development Programme",
        "fcerm",
    ),
    _org("food-standards-agency", "Food Standards Agency", "fsa"),
    _org("forest-enterprise-england", "Forest Enterprise England"),
    _org("forest-research", "Forest Research"),
    _org("forest-service", "Forest Service"),
    _org("forestry-commission", "Forestry Commission"),
    _org("government-chemist", "Government Chemist"),
    _org("government-office-for-science", "Government Office for Science"),
    _org("high-speed-two-limited", "High Speed Two Limited", "hs2"),
    _org("hm-revenue-customs", "HM Revenue & Customs", "hmrc"),
    _org("joint-nature-conservation-committee", "Joint Nature Conservation Committee", "jncc"),
    _org("marine-fisheries-agency", "Marine Fisheries Agency"),
    _org("marine-management-organisation", "Marine Management Organisation", "mmo"),
    _org("maritime-and-coastguard-agency", "Maritime and Coastguard Agency", "mca"),
    _org(
        "ministry-of-housing-communities-and-local-government",
        "Ministry of Housing, Communities and Local Government",
        "mhclg",
    ),
    _org("national-forest-company", "National Forest Company"),
    _org("natural-england", "Natural England"),
    _org("office-for-environmental-protection", "Office for Environmental Protection", "oep"),
    _org("plant-varieties-and-seeds-tribunal", "Plant Varieties and Seeds Tribunal"),
    _org("rural-development-programme-for-england-network", "Rural Development Programme for England Network", "rdpe"),
    _org("rural-payments-agency", "Rural Payments Agency", "rpa"),
    _org("sellafield-ltd", "Sellafield Ltd"),
    _org("state-veterinary-service", "State Veterinary Service"),
    _org("the-food-and-environment-research-agency", "The Food and Environment Research Agency", "fera"),
    _org("valuation-office-agency", "Valuation Office Agency", "voa"),
    _org("veterinary-laboratories-agency", "Veterinary Laboratories Agency", "vla"),
    _org("veterinary-medicines-directorate", "Veterinary Medicines Directorate", "vmd"),
    _org("veterinary-products-committee", "Veterinary Products Committee", "vpc"),
)


def organisation_options_for(
    slugs: list[str] | tuple[str, ...],
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    overlay = {value: (label, aliases) for value, label, aliases in ORGANISATION_OPTIONS}
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for slug in slugs:
        if slug in overlay:
            label, aliases = overlay[slug]
        else:
            label, aliases = title_from_slug(slug), ()
        out.append((slug, label, aliases))
    return tuple(out)


def document_type_options_for(
    slugs: list[str] | tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    overlay = {value: label for value, label in DOCUMENT_TYPE_OPTIONS}
    return tuple((slug, overlay.get(slug) or title_from_slug(slug)) for slug in slugs)


def scope_options(
    organisations: list[str] | tuple[str, ...],
    document_types: list[str] | tuple[str, ...],
) -> tuple[tuple[tuple[str, str, tuple[str, ...]], ...], tuple[tuple[str, str], ...]]:
    return organisation_options_for(organisations), document_type_options_for(document_types)


def _normalized_set(values: list[str] | tuple[str, ...]) -> set[str]:
    return {norm for v in values if (norm := normalize_slug(v))}


def page_matches_organisations(page: dict[str, Any], needles: list[str] | tuple[str, ...]) -> bool:
    if not needles:
        return True
    wanted = _normalized_set(list(needles))
    if not wanted:
        return True
    md = page.get("meta_data") or {}
    values = [md.get("primary_publishing_organisation") or ""]
    values.extend(md.get("organisations") or [])
    return bool(wanted & _normalized_set(values))


def page_matches_document_types(page: dict[str, Any], needles: list[str] | tuple[str, ...]) -> bool:
    if not needles:
        return True
    wanted = _normalized_set(list(needles))
    if not wanted:
        return True
    md = page.get("meta_data") or {}
    got = normalize_slug(md.get("document_type") or "")
    return bool(got) and got in wanted


def split_matching(
    pages: list[dict[str, Any]],
    match_fn: Callable[[dict[str, Any], list[str] | tuple[str, ...]], bool],
    needles: list[str] | tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not needles:
        return list(pages), []
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for page in pages:
        (kept if match_fn(page, needles) else dropped).append(page)
    return kept, dropped


def filter_pages(
    pages: list[dict[str, Any]],
    *,
    organisations: list[str] | tuple[str, ...] = (),
    document_types: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    kept, _dropped = split_matching(pages, page_matches_organisations, organisations)
    kept, _dropped = split_matching(kept, page_matches_document_types, document_types)
    return kept


def unmatched_scope_warnings(
    pages: list[dict[str, Any]],
    *,
    organisations: list[str] | tuple[str, ...] = (),
    document_types: list[str] | tuple[str, ...] = (),
) -> list[str]:
    warnings: list[str] = []
    for needle in organisations or ():
        if not any(page_matches_organisations(page, [needle]) for page in pages):
            warnings.append(
                f"organisation {needle!r} matched no pages on this index"
            )
    for needle in document_types or ():
        if not any(page_matches_document_types(page, [needle]) for page in pages):
            warnings.append(
                f"document type {needle!r} matched no pages on this index"
            )
    return warnings


def unmatched_scope_warnings_index(
    index,
    *,
    organisations: list[str] | tuple[str, ...] = (),
    document_types: list[str] | tuple[str, ...] = (),
) -> list[str]:
    warnings: list[str] = []
    for needle in organisations or ():
        if not index.has_organisation(needle):
            warnings.append(
                f"organisation {needle!r} matched no pages on this index"
            )
    for needle in document_types or ():
        if not index.has_document_type(needle):
            warnings.append(
                f"document type {needle!r} matched no pages on this index"
            )
    return warnings


def packaged_templates() -> dict[str, dict[str, Any]]:
    data = files("guidance_relevance_filter.data")
    out: dict[str, dict[str, Any]] = {}
    for key, cat_name, lex_name in (
        ("fish", "categories.json", "lexicon.json"),
        ("slurry", "categories-slurry.json", "lexicon-slurry.json"),
    ):
        categories = json.loads((data / cat_name).read_text())
        lexicons = json.loads((data / lex_name).read_text())
        cat = categories[0]
        name = cat["name"]
        out[key] = {
            "name": name,
            "description": cat.get("description") or "",
            "exclusion_criteria": cat.get("exclusion_criteria") or "",
            "keep_hints": "\n".join((cat.get("adjudication_hints") or {}).get("keep") or []),
            "drop_hints": "\n".join((cat.get("adjudication_hints") or {}).get("drop") or []),
            "lexicon": "\n".join(lexicons.get(name) or []),
        }
    return out
