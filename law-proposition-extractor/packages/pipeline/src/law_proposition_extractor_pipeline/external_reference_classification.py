"""Deterministic classification of external standards and technical references in law text."""

from __future__ import annotations

import re
from typing import Any, Literal

ExternalReferenceKind = Literal[
    "external_standard_reference",
    "external_guidance_reference",
    "external_certification_reference",
]

ResolutionStatus = Literal["external_reference"]

# Long-form: paragraph(s) … code of practice … BS 5502: Part N: YYYY
_LONG_BS_CODE_RE = re.compile(
    r"(?:in accordance with\s+)?"
    r"(?P<para>paragraphs?\s+[\d.]+(?:\s+to\s+[\d.]+)?\s+of\s+the\s+)?"
    r"code of practice[^.;]+?"
    r"(?:published by the British Standards Institution and\s+)?"
    r"numbered\s+"
    r"(?P<bs>BS\s*5502\s*:\s*Part\s*\d+\s*:\s*\d{4})",
    re.IGNORECASE,
)

# paragraph(s) X of BS 5502 (Part N: YYYY)
_BS_5502_PARA_OF_PAREN_RE = re.compile(
    r"(?P<para>paragraphs?\s+[\d.]+(?:\s+to\s+[\d.]+)?)\s+of\s+"
    r"(?P<bs>BS\s*5502\s*\(Part\s*\d+\s*:\s*\d{4}\))",
    re.IGNORECASE,
)

# BS 5502 (Part N: YYYY)[, paragraph(s) X]
_BS_5502_PAREN_PARA_RE = re.compile(
    r"(?P<bs>BS\s*5502\s*\(Part\s*\d+\s*:\s*\d{4}\))"
    r"(?:\s*,\s*(?P<para>paragraphs?\s+[\d.]+(?:\s+to\s+[\d.]+)?))?",
    re.IGNORECASE,
)

# BS 5502: Part 50:1993[, paragraph 7] or Part 22: 1993, paragraph 15.6.1 to 15.6.3
_BS_5502_SHORT_RE = re.compile(
    r"(?P<bs>BS\s*5502\s*:\s*Part\s*\d+\s*:\s*\d{4})"
    r"(?:\s*,\s*(?P<para>paragraph\s+[\d.]+(?:\s+to\s+[\d.]+)?))?",
    re.IGNORECASE,
)

# Other numbered BS standards (BS 8007: 1987, BS 5502: Part 21: 1990)
_BS_GENERAL_RE = re.compile(
    r"\bBS\s*\d+(?:\s*\d+)?\s*:\s*(?:Part\s*\d+\s*:\s*)?\d{4}\b",
    re.IGNORECASE,
)

_RB209_RE = re.compile(
    r"Nutrient Management Guide\s*\(\s*RB209\s*\)",
    re.IGNORECASE,
)

_FERTILISER_MANUAL_RE = re.compile(
    r"(?:the\s+)?Fertiliser Manual(?:\s+RB209)?",
    re.IGNORECASE,
)

_RB209_BARE_RE = re.compile(r"\bRB209\b", re.IGNORECASE)

_FACTS_SCHEME_RE = re.compile(
    r"Fertiliser Advisers Certification and Training Scheme|\bFACTS adviser\b",
    re.IGNORECASE,
)

_BSI_MENTION_RE = re.compile(
    r"British Standards?\s+Institution|\bBSI\b",
    re.IGNORECASE,
)

_MALFORMED_BS_RE = re.compile(
    r"\bBS\s*5502\s*:\s*Part\s*(?!(\d+\s*:\s*\d{4}))",
    re.IGNORECASE,
)

_STANDARDS_CUE_RE = (
    r"designed and constructed in accordance with"
    r"|designed in accordance with"
    r"|constructed in accordance with"
    r"|in accordance with"
    r"|comply with"
    r"|complies with"
    r"|designed to"
    r"|constructed to"
    r"|as specified in"
    r"|as set out in"
)

_BARE_STANDARD_CODE_BODY = (
    r"BS(?:\s+EN(?:\s+ISO)?)?\s+\d+"
    r"|ISO\s+\d+"
    r"|EN\s+\d+"
)

_BARE_STANDARD_AFTER_CUE_RE = re.compile(
    rf"(?:{_STANDARDS_CUE_RE})\s+(?P<code>{_BARE_STANDARD_CODE_BODY})\b",
    re.IGNORECASE,
)

_BRITISH_STANDARD_WITH_CODE_RE = re.compile(
    r"British\s+Standards?\s+(?P<code>BS(?:\s+EN(?:\s+ISO)?)?\s+\d+)\b",
    re.IGNORECASE,
)

_RELEVANT_BRITISH_STANDARD_RE = re.compile(
    rf"(?:{_STANDARDS_CUE_RE})\s+(?:the\s+)?(?:any\s+)?relevant\s+British\s+Standard\b",
    re.IGNORECASE,
)

_BARE_STANDARD_SUFFIX_RE = re.compile(
    r"\s*:\s*(?:Part\b|(?:Part\s*\d+\s*:\s*)?\d{4}\b)|\s*\(Part\b",
    re.IGNORECASE,
)

_GENERIC_BRITISH_STANDARD_LOCATORS = frozenset(
    {
        "british standard",
        "the relevant british standard",
        "any relevant british standard",
    }
)

_INTERNAL_PARAGRAPH_RE = re.compile(
    r"^paragraph\s+(\d+[a-z]?)(?:\(([^)]+)\))?$",
    re.IGNORECASE,
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _normalize_para_clause(para: str | None) -> str | None:
    if not para:
        return None
    para_clean = _collapse_ws(para)
    para_clean = re.sub(r"\s+of\s+the\s*$", "", para_clean, flags=re.IGNORECASE)
    para_clean = re.sub(r"^paragraphs\b", "paragraph", para_clean, flags=re.IGNORECASE)
    if not para_clean.lower().startswith("paragraph"):
        para_clean = f"paragraph {para_clean}"
    return para_clean


def _external_reference_specificity_score(locator: str) -> int:
    """Higher score means a more specific external reference locator."""
    loc = _collapse_ws(locator).lower()
    if loc in _GENERIC_BRITISH_STANDARD_LOCATORS:
        return 0
    if re.search(r"\bpart\s+\d+|\(part\s+\d+", loc):
        return 4
    if re.search(r":\s*\d{4}\b", loc):
        return 3
    if re.match(r"^(?:bs(?:\s+en(?:\s+iso)?)?|iso|en)\s+\d+", loc):
        return 2
    return 1


def _bare_standard_root(locator: str) -> str | None:
    loc = _collapse_ws(locator)
    match = re.match(
        r"^(BS(?:\s+EN(?:\s+ISO)?)?\s+\d+|ISO\s+\d+|EN\s+\d+)",
        loc,
        re.IGNORECASE,
    )
    return _collapse_ws(match.group(1)).upper() if match else None


def dedupe_external_references_by_span_and_specificity(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer the most specific external locator when patterns overlap."""
    ranked = sorted(
        entries,
        key=lambda row: (
            _external_reference_specificity_score(str(row.get("locator") or "")),
            len(str(row.get("locator") or "")),
        ),
        reverse=True,
    )
    pruned: list[dict[str, Any]] = []
    for entry in ranked:
        loc = str(entry.get("locator") or "").lower()
        if not loc:
            continue
        if any(
            loc != str(other.get("locator") or "").lower()
            and loc in str(other.get("locator") or "").lower()
            for other in pruned
        ):
            continue
        root = _bare_standard_root(str(entry.get("locator") or ""))
        if root and any(
            _bare_standard_root(str(other.get("locator") or "")) == root
            and _external_reference_specificity_score(str(other.get("locator") or ""))
            > _external_reference_specificity_score(str(entry.get("locator") or ""))
            for other in pruned
        ):
            continue
        if loc in _GENERIC_BRITISH_STANDARD_LOCATORS and any(
            _bare_standard_root(str(other.get("locator") or "")) is not None for other in pruned
        ):
            continue
        pruned.append(entry)
    return pruned


def _prune_subsumed_external_locators(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer the most specific external locator when long- and short-form patterns overlap."""
    return dedupe_external_references_by_span_and_specificity(entries)


def _normalize_bare_standard_code(code: str) -> str:
    normalized = _collapse_ws(code)
    if normalized.upper().startswith("BS"):
        return re.sub(
            r"^BS(?:\s+EN(?:\s+ISO)?)?",
            lambda match: match.group(0).upper(),
            normalized,
            count=1,
            flags=re.IGNORECASE,
        )
    if normalized.upper().startswith("ISO"):
        return re.sub(r"^ISO", "ISO", normalized, count=1, flags=re.IGNORECASE)
    if normalized.upper().startswith("EN"):
        return re.sub(r"^EN", "EN", normalized, count=1, flags=re.IGNORECASE)
    return normalized


def _bare_standard_entry(code: str) -> dict[str, Any]:
    return {
        "kind": "external_standard_reference",
        "locator": _normalize_bare_standard_code(code),
        "resolution_status": "external_reference",
        "proposition_ids": [],
        "malformed": False,
    }


def _is_specific_standard_suffix(text: str, start: int) -> bool:
    return bool(_BARE_STANDARD_SUFFIX_RE.match(text[start:]))


def _extract_bare_standard_references(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    for pattern in (_BARE_STANDARD_AFTER_CUE_RE, _BRITISH_STANDARD_WITH_CODE_RE):
        for match in pattern.finditer(text):
            code = match.group("code") or ""
            if not code or _is_specific_standard_suffix(text, match.end("code")):
                continue
            entry = _bare_standard_entry(code)
            key = entry["locator"].lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(entry)

    for match in _RELEVANT_BRITISH_STANDARD_RE.finditer(text):
        locator = _collapse_ws(match.group(0))
        locator = re.sub(
            rf"^(?:{_STANDARDS_CUE_RE})\s+",
            "",
            locator,
            count=1,
            flags=re.IGNORECASE,
        )
        locator = _collapse_ws(locator)
        key = locator.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "kind": "external_standard_reference",
                "locator": locator,
                "resolution_status": "external_reference",
                "proposition_ids": [],
                "malformed": False,
            }
        )

    return found


def _locator_from_bs_match(
    *,
    bs: str,
    para: str | None,
    kind: ExternalReferenceKind = "external_standard_reference",
) -> dict[str, Any]:
    bs_clean = _collapse_ws(bs)
    locator = bs_clean
    para_clean = _normalize_para_clause(para)
    if para_clean:
        locator = f"{bs_clean}, {para_clean}"
    return {
        "kind": kind,
        "locator": locator,
        "resolution_status": "external_reference",
        "proposition_ids": [],
        "malformed": False,
    }


def _extract_bs_references(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    for pattern in (_LONG_BS_CODE_RE, _BS_5502_PARA_OF_PAREN_RE, _BS_5502_PAREN_PARA_RE):
        for match in pattern.finditer(text):
            bs = match.group("bs") or ""
            para = match.group("para") or ""
            entry = _locator_from_bs_match(bs=bs, para=para or None)
            key = entry["locator"].lower()
            if key not in seen:
                seen.add(key)
                found.append(entry)

    for match in _BS_5502_SHORT_RE.finditer(text):
        bs = match.group("bs") or ""
        para = match.group("para") or ""
        entry = _locator_from_bs_match(bs=bs, para=para or None)
        key = entry["locator"].lower()
        if key not in seen:
            seen.add(key)
            found.append(entry)

    for match in _BS_GENERAL_RE.finditer(text):
        bs = match.group(0)
        if re.search(r"BS\s*5502", bs, re.IGNORECASE):
            continue
        entry = _locator_from_bs_match(bs=bs, para=None)
        key = entry["locator"].lower()
        if key not in seen:
            seen.add(key)
            found.append(entry)

    for entry in _extract_bare_standard_references(text):
        key = entry["locator"].lower()
        if key not in seen:
            seen.add(key)
            found.append(entry)

    return found


def _extract_guidance_references(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    for pattern in (_RB209_RE, _FERTILISER_MANUAL_RE):
        for match in pattern.finditer(text):
            locator = _collapse_ws(match.group(0))
            key = locator.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "kind": "external_guidance_reference",
                    "locator": locator,
                    "resolution_status": "external_reference",
                    "proposition_ids": [],
                    "malformed": False,
                }
            )

    if _RB209_BARE_RE.search(text) and not seen:
        for match in _RB209_BARE_RE.finditer(text):
            locator = "RB209"
            if "nutrient management guide" in text.lower():
                locator = "Nutrient Management Guide (RB209)"
            key = locator.lower()
            if key not in seen:
                seen.add(key)
                found.append(
                    {
                        "kind": "external_guidance_reference",
                        "locator": locator,
                        "resolution_status": "external_reference",
                        "proposition_ids": [],
                        "malformed": False,
                    }
                )

    return found


def _extract_certification_references(text: str) -> list[dict[str, Any]]:
    if not _FACTS_SCHEME_RE.search(text):
        return []
    return [
        {
            "kind": "external_certification_reference",
            "locator": "Fertiliser Advisers Certification and Training Scheme (FACTS)",
            "resolution_status": "external_reference",
            "proposition_ids": [],
            "malformed": False,
        }
    ]


def _malformed_external_entries(text: str) -> list[dict[str, Any]]:
    if not _MALFORMED_BS_RE.search(text):
        return []
    snippet = _collapse_ws(_MALFORMED_BS_RE.search(text).group(0))  # type: ignore[union-attr]
    return [
        {
            "kind": "external_standard_reference",
            "locator": snippet,
            "resolution_status": "external_reference",
            "proposition_ids": [],
            "malformed": True,
        }
    ]


def extract_external_references(text: str) -> list[dict[str, Any]]:
    """Extract external standard/guidance references from proposition text."""
    if not str(text or "").strip():
        return []
    combined: list[dict[str, Any]] = []
    combined.extend(_extract_bs_references(text))
    combined.extend(_extract_guidance_references(text))
    combined.extend(_extract_certification_references(text))

    malformed = _malformed_external_entries(text)
    if malformed and not combined:
        combined.extend(malformed)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in combined:
        key = str(entry.get("locator") or "").lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(entry)
    return _prune_subsumed_external_locators(deduped)


def _text_has_external_standard_cue(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\bBS\s*\d+", text, re.IGNORECASE)
        or _BSI_MENTION_RE.search(text)
        or "british standard" in lowered
    )


def internal_locator_subsumed_by_external(
    target: str,
    *,
    text: str,
    external_refs: list[dict[str, Any]],
) -> bool:
    """
    Return True when an internal locator (e.g. paragraph 7) is part of an external standard cite.
    """
    if not _text_has_external_standard_cue(text):
        return False

    target_norm = target.strip().lower()
    match = _INTERNAL_PARAGRAPH_RE.match(target_norm.replace(":", " "))
    if not match:
        return False

    para_num = match.group(1).lower()
    sub = match.group(2)
    para_phrase = f"paragraph {para_num}"
    if sub:
        para_phrase = f"paragraph {para_num}({sub.lower()})"

    for entry in external_refs:
        if entry.get("kind") != "external_standard_reference":
            continue
        locator = str(entry.get("locator") or "").lower()
        if para_phrase in locator or f"paragraph {para_num}" in locator:
            return True

    bs_para_cite = re.search(
        rf"paragraphs?\s+{re.escape(para_num)}(?:\.\d+)?(?:\s+to\s+[\d.]+)?\s+of\s+bs\s*5502",
        text,
        re.IGNORECASE,
    )
    if bs_para_cite:
        return True

    if re.search(
        rf"paragraphs?\s+{re.escape(para_num)}(?:\.\d+)?\s+of\s+bs\s*5502",
        text,
        re.IGNORECASE,
    ):
        return True

    return False


def filter_internal_reference_targets(
    targets: list[str],
    *,
    text: str,
    external_refs: list[dict[str, Any]],
) -> list[str]:
    """Drop internal locator targets that are explained by an external reference in the same text."""
    kept: list[str] = []
    for target in targets:
        if internal_locator_subsumed_by_external(target, text=text, external_refs=external_refs):
            continue
        kept.append(target)
    return kept


def external_context_entries_for_proposition(
    prop: dict[str, Any],
    *,
    internal_targets: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Return external required_context entries and internal targets with external-only
    paragraph locators removed.
    """
    text = str(prop.get("proposition_text") or "")
    external_refs = extract_external_references(text)
    filtered_targets = filter_internal_reference_targets(
        internal_targets,
        text=text,
        external_refs=external_refs,
    )
    return external_refs, filtered_targets
