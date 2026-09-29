"""Query normalisation and alias expansion for legislation.gov.uk-related source search."""

from __future__ import annotations

import re
from typing import Any

AnimalHealthPhrase = dict[str, Any]

AH_HINT = "eur/2016/429"


def squash_ws(value: str) -> str:
    return " ".join(value.split())


def _strip_celex_noise(value: str) -> str:
    return re.sub(r"(?i)^celex\s*:\s*", "", value.strip()).strip()


def eu_celex_to_legislation_authority_source_id(celex_token: str) -> str | None:
    """Map CELEX (e.g. ``32016R0429``) to legislation.gov.uk ``eur/{{year}}/{{number}}``.

    Maps sector ``3`` + regulation ``R`` to the consolidated EU instrument path on legislation.gov.uk.
    """

    trimmed = squash_ws(celex_token)
    trimmed = _strip_celex_noise(trimmed)
    compact = re.sub(r"\s+", "", trimmed)
    matched = re.fullmatch(r"(?P<sector>[123])(?P<year>\d{4})(?P<kind>[RLDMCA])(?P<num>\d{2,})", compact, re.I)
    if matched is None:
        return None
    if matched.group("sector") != "3":
        return None
    if matched.group("kind").upper() != "R":
        return None
    year = matched.group("year")
    num = str(int(matched.group("num")))
    return f"eur/{year}/{num}"


def _animal_health_aliases() -> list[AnimalHealthPhrase]:
    rows: list[AnimalHealthPhrase] = []
    for normalized in ("animal health law", "animal health regulation", "transmissible animal diseases"):
        rows.append(
            {
                "normalized": normalized,
                "hints": (AH_HINT,),
                "match": "substring",
            }
        )
    rows.extend(
        [
            {"normalized": "animal health", "hints": (AH_HINT,), "match": "exact"},
            {"normalized": "ahl", "hints": (AH_HINT,), "match": "exact"},
            {"normalized": "a h l", "hints": (AH_HINT,), "match": "exact"},
        ]
    )
    return rows


PHRASE_ALIASES: list[AnimalHealthPhrase] = _animal_health_aliases()


def _hint_prepend(seq: list[str], value: str) -> None:
    if value in seq:
        seq.remove(value)
    seq.insert(0, value)


def authority_source_ids_hinted_for_query(raw: str) -> list[str]:
    """Return hints (``series/year/number``) to try resolving before title search."""

    trimmed = raw.strip()
    if len(trimmed) < 2:
        return []

    hints: list[str] = []
    lowered_compact = squash_ws(trimmed.lower())

    slash_euri = re.search(
        r"(?:^|\s)(?:eur|EUR)\s*/\s*(?P<year>20\d{2})\s*/\s*(?P<num>\d{3,})\b",
        trimmed,
        re.IGNORECASE,
    )
    if slash_euri:
        _hint_prepend(hints, f"eur/{slash_euri.group('year')}/{int(slash_euri.group('num'))}")

    eu_plain = re.search(
        r"\b(?:EUR|EU)\s+(?P<year>20\d{2})\s*/\s*(?P<num>\d{3,})\b",
        trimmed,
        re.IGNORECASE,
    )
    if eu_plain:
        _hint_prepend(hints, f"eur/{eu_plain.group('year')}/{int(eu_plain.group('num'))}")

    for token in squash_ws(trimmed).replace(";", " ").replace(",", " ").split():
        cid = eu_celex_to_legislation_authority_source_id(token)
        if cid:
            _hint_prepend(hints, cid)

    for grp in re.findall(r"\b(3\s*\d{4}\s*[Rr]\s*\d{3,})\b", trimmed):
        cid = eu_celex_to_legislation_authority_source_id(re.sub(r"\s+", "", grp))
        if cid:
            _hint_prepend(hints, cid)

    regulation_year_num = re.search(
        r"(?i)\bregulation\b[^0-9]{0,48}(?P<year>20\d{2})\s*/\s*(?P<num>\d{3,})\b",
        trimmed,
    )
    if regulation_year_num:
        _hint_prepend(hints, f"eur/{regulation_year_num.group('year')}/{int(regulation_year_num.group('num'))}")

    m_year_num = re.search(
        r"(?<!/)(?P<year>20\d{2})\s*/\s*(?P<num>\d{3,})\b",
        trimmed,
        flags=re.IGNORECASE,
    )
    if m_year_num:
        _hint_prepend(hints, f"eur/{m_year_num.group('year')}/{int(m_year_num.group('num'))}")

    norm_comp = lowered_compact.replace("-", " ")
    for phrase_row in PHRASE_ALIASES:
        phrase = str(phrase_row["normalized"])
        mode = str(phrase_row.get("match", "substring"))
        if mode == "exact":
            if norm_comp != phrase:
                continue
        elif phrase not in norm_comp:
            continue
        for aid in phrase_row["hints"]:
            if aid not in hints:
                hints.append(aid)

    return hints


def summarise_query_resolution(raw_query: str, hints: list[str]) -> dict[str, Any]:
    return {
        "original_query": raw_query,
        "authority_source_id_hints": list(hints),
    }
