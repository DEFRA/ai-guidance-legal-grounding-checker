"""Canonical territory names and conservative text extraction for UK/EU law."""

from __future__ import annotations

import re
from typing import Literal

TerritoryExtractionContext = Literal["extent", "application_scope", "mention"]

# Canonical labels used in territorial_application / extent arrays.
CANONICAL_TERRITORIES = frozenset(
    {
        "England",
        "Wales",
        "Scotland",
        "Northern Ireland",
        "Great Britain",
        "United Kingdom",
        "EU",
        "Member State",
    }
)

_UK_NATIONS = frozenset({"England", "Wales", "Scotland", "Northern Ireland"})

_SOURCE_JURISDICTION_ALIASES: dict[str, str] = {
    "uk": "UK",
    "u.k.": "UK",
    "gb": "UK",
    "gbr": "UK",
    "great britain": "UK",
    "united kingdom": "UK",
    "eu": "EU",
    "e.u.": "EU",
    "european union": "EU",
    "union": "EU",
    "england": "England",
    "wales": "Wales",
    "scotland": "Scotland",
    "northern ireland": "Northern Ireland",
}

_TERRITORY_ALIASES: dict[str, str] = {
    "england": "England",
    "wales": "Wales",
    "scotland": "Scotland",
    "northern ireland": "Northern Ireland",
    "great britain": "Great Britain",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "gb": "Great Britain",
    "eu": "EU",
    "e.u.": "EU",
    "european union": "EU",
    "the union": "EU",
    "union": "EU",
    "member state": "Member State",
    "member states": "Member State",
    "each member state": "Member State",
}

_PLACE_NAME_RE = re.compile(
    r"\b(England|Wales|Scotland|Northern Ireland|Great Britain|United Kingdom|"
    r"Member States?|the Union|European Union)\b",
    re.IGNORECASE,
)


def normalize_source_jurisdiction(raw: str) -> str:
    """
    Normalise law-making / source jurisdiction from a source record field.

    Sub-UK nations on a UK-hosted instrument still map to UK for source_jurisdiction
    unless the source is explicitly tagged with that nation as the law-making body.
    """
    key = str(raw or "").strip().lower()
    if not key:
        return ""
    mapped = _SOURCE_JURISDICTION_ALIASES.get(key)
    if mapped:
        return mapped
    title = key.title()
    if title in CANONICAL_TERRITORIES:
        return title
    return str(raw).strip()


def normalize_territory_name(raw: str) -> str | None:
    """
    Normalise a territory mention for extent / territorial_application arrays.

    Returns None when the token is not a recognised territory (conservative).
    """
    key = str(raw or "").strip().lower()
    if not key:
        return None
    key = re.sub(r"^the\s+", "", key)
    mapped = _TERRITORY_ALIASES.get(key)
    if mapped:
        return mapped
    title = key.title()
    if title in CANONICAL_TERRITORIES:
        return title
    return None


def split_territory_list(segment: str) -> list[str]:
    """Split 'England and Wales' / comma lists into canonical territory names."""
    segment = segment.strip(" .,;")
    if not segment:
        return []
    parts = re.split(r"\s+and\s+|,\s*", segment, flags=re.IGNORECASE)
    out: list[str] = []
    for part in parts:
        part = re.sub(r"^the\s+", "", part.strip(), flags=re.IGNORECASE)
        for m in _PLACE_NAME_RE.finditer(part):
            place = normalize_territory_name(m.group(1))
            if place and place not in out:
                out.append(place)
        if not _PLACE_NAME_RE.search(part):
            norm = normalize_territory_name(part)
            if norm and norm not in out:
                out.append(norm)
    return out[:8]


def extract_territories_from_text(
    text: str,
    *,
    context: TerritoryExtractionContext = "mention",
) -> list[str]:
    """
    Extract recognised territories only when phrasing is explicit enough.

    - extent: 'extend(s) to …'
    - application_scope: 'apply/applies to …', 'apply in relation to …', 'in England' after apply
    - mention: bare place names (still conservative — known tokens only)
    """
    if not str(text or "").strip():
        return []
    src = str(text)
    out: list[str] = []

    if context in {"extent", "mention"}:
        m = re.search(r"\bextends?\s+to\s+(.+?)(?:\.|;|$)", src, re.IGNORECASE)
        if m:
            for place in split_territory_list(m.group(1)):
                if place not in out:
                    out.append(place)
            if out:
                return out[:8]

    if context in {"application_scope", "mention"}:
        m = re.search(
            r"\bapply(?:s)?(?:\s+in relation)?\s+to\s+(.+?)(?:\.|;|$)",
            src,
            re.IGNORECASE,
        )
        if m:
            target = m.group(1).strip()
            in_m = re.search(
                r"^(.+?)\s+in\s+(England|Wales|Scotland|Northern Ireland)(?:\s+only)?\s*$",
                target,
                re.IGNORECASE,
            )
            if in_m:
                place = normalize_territory_name(in_m.group(2))
                if place and place not in out:
                    out.append(place)
            else:
                for place in split_territory_list(target):
                    if place not in out:
                        out.append(place)
            if out:
                return out[:8]

    if context == "mention":
        for m in _PLACE_NAME_RE.finditer(src):
            place = normalize_territory_name(m.group(1))
            if place and place not in out:
                out.append(place)
    return out[:8]


def coerce_source_jurisdiction_for_proposition(
    *,
    coarse_jurisdiction: str,
    explicit_source_jurisdiction: str | None = None,
    source_metadata: dict | None = None,
) -> str:
    """Derive source_jurisdiction for a proposition from source fields."""
    meta = source_metadata or {}
    explicit = normalize_source_jurisdiction(
        str(explicit_source_jurisdiction or meta.get("source_jurisdiction") or "")
    )
    if explicit in {"UK", "EU"}:
        return explicit
    if explicit in _UK_NATIONS:
        return "UK"
    if explicit:
        return explicit

    coarse = normalize_source_jurisdiction(coarse_jurisdiction)
    if coarse in _UK_NATIONS:
        return "UK"
    if coarse:
        return coarse
    return str(coarse_jurisdiction or "").strip()
