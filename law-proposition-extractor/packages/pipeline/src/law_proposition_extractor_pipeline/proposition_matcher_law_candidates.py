"""Deterministic Proposition Matcher-facing law candidate export from effective law statements."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from law_proposition_extractor_domain.proposition_jurisdiction import extent_from_source_metadata
from law_proposition_extractor_domain.territory_normalization import normalize_territory_name, split_territory_list
from law_proposition_extractor_pipeline.effective_law import normalize_cross_reference_locator

CandidateStatus = Literal["ready", "usable_with_context", "needs_review"]
MatchRole = Literal["primary_law_candidate"]

_SCHEMA_VERSION = "1"
_SUMMARY_MAX_LEN = 2000
_TITLE_TRUNC_LEN = 120
_MATCHING_TEXT_MAX_LEN = 4000
_PROP_LABEL_TRUNC_LEN = 80

_CANDIDATE_STATUS_RANK = {"ready": 0, "usable_with_context": 1, "needs_review": 2}

_EXCLUDED_PRESENTATION_ROLES = frozenset(
    {
        "context_connector",
        "supporting_definition",
        "procedural_or_enforcement_context",
        "debug_only",
    }
)

_EXCLUDED_STANDALONE_STATUSES = frozenset({"relationship_only", "fragmentary"})

_WIRING_CONTEXT_KINDS = frozenset(
    {
        "host_rule",
        "incorporated_rule",
        "incorporated_factors",
    }
)

_UK_NATION_TERRITORIES = frozenset({"England", "Wales", "Scotland", "Northern Ireland"})
_UK_NATION_ORDER = ("England", "Wales", "Scotland", "Northern Ireland")

_EXTENT_ALIASES: dict[str, list[str]] = {
    "e&w": ["England", "Wales"],
    "e and w": ["England", "Wales"],
    "england and wales": ["England", "Wales"],
    "england_wales": ["England", "Wales"],
}

_CITATION_WSI_RE = re.compile(r"\bWSI\b", re.IGNORECASE)
_CITATION_SSI_RE = re.compile(r"\bSSI\b", re.IGNORECASE)
_TITLE_WALES_RE = re.compile(r"\(Wales\)|\bWales Regulations\b", re.IGNORECASE)
_TITLE_SCOTLAND_RE = re.compile(r"\(Scotland\)|\bScotland Regulations\b", re.IGNORECASE)
_TITLE_ENGLAND_RE = re.compile(r"\(England\)|\bEngland Regulations\b", re.IGNORECASE)
_TITLE_ENGLAND_AND_WALES_RE = re.compile(r"England and Wales", re.IGNORECASE)

_COLON_PARAGRAPH_PATH_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|part|annex|rule):"
    r"(?P<num>\d+[a-z]?):"
    r"paragraph:(?P<rest>.+)$",
    re.IGNORECASE,
)

_STRUCTURED_LIMB_RE = re.compile(
    r"^(?P<para>\d+[a-z]?):subparagraph:(?P<sub>[a-z0-9]+)"
    r"(?::items?:(?P<item>[a-z0-9]+(?:-[a-z0-9]+)?))?$",
    re.IGNORECASE,
)

_LIST_LIMB_RE = re.compile(
    r"^(?P<para>\d+[a-z]?):list:(?P<echo>\d+[a-z]?)-(?P<sub>[a-z0-9]+)"
    r"(?:-(?P<item>[a-z0-9]+))?$",
    re.IGNORECASE,
)

_PAREN_LIMB_RE = re.compile(
    r"^(?P<para>\d+[a-z]?)[:\s]*(?P<parens>\(.+\))$",
    re.IGNORECASE,
)

_SPACE_SCHEDULE_PARA_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|part|annex|rule)\s+"
    r"(?P<num>\d+[a-z]?)\s*,\s*paragraph\s+"
    r"(?P<para>\d+[a-z]?)(?:\s*\((?P<sub>.+)\))?$",
    re.IGNORECASE,
)

_SPACE_INSTRUMENT_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|part|annex|rule)\s+"
    r"(?P<num>\d+[a-z]?)"
    r"(?P<parens>(?:\([^)]+\))+)?$",
    re.IGNORECASE,
)

_CHAPEAU_STEM_RE = re.compile(
    r"^(?:"
    r"subject to paragraph\b|"
    r"these regulations do not apply\b|"
    r"subject to paragraph \(\d+\)"
    r")",
    re.IGNORECASE,
)

_LOCATOR_ENCODING_STRUCTURED = "structured"
_LOCATOR_ENCODING_LIST = "list"
_LOCATOR_ENCODING_PAREN = "paren"
_LOCATOR_ENCODING_OTHER = "other"

_ENCODING_RANK = {
    _LOCATOR_ENCODING_STRUCTURED: 0,
    _LOCATOR_ENCODING_LIST: 1,
    _LOCATOR_ENCODING_PAREN: 2,
    _LOCATOR_ENCODING_OTHER: 3,
}


def _stable_hash(parts: tuple[str, ...]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _split_paren_limb_tokens(parens: str) -> list[str]:
    """Split ``(a)(i)`` / ``(b)(i)-(ii)`` into limb tokens (ranges kept as ``i-ii``)."""
    tokens: list[str] = []
    for match in re.finditer(r"\(([^)]+)\)(?:-\(([^)]+)\))?", parens):
        left = match.group(1).strip().lower()
        right = (match.group(2) or "").strip().lower()
        if right:
            tokens.append(f"{left}-{right}")
        elif left:
            tokens.append(left)
    return tokens


def _limbs_from_paragraph_rest(rest: str) -> tuple[str, list[str]] | None:
    """Return ``(paragraph_num, limb_tokens)`` from the text after ``:paragraph:``."""
    text = str(rest or "").strip().lower()
    if not text:
        return None

    structured = _STRUCTURED_LIMB_RE.match(text)
    if structured:
        limbs = [structured.group("sub").lower()]
        item = structured.group("item")
        if item:
            limbs.append(item.lower())
        return structured.group("para").lower(), limbs

    list_match = _LIST_LIMB_RE.match(text)
    if list_match:
        limbs = [list_match.group("sub").lower()]
        item = list_match.group("item")
        if item:
            limbs.append(item.lower())
        return list_match.group("para").lower(), limbs

    paren_match = _PAREN_LIMB_RE.match(text)
    if paren_match:
        return paren_match.group("para").lower(), _split_paren_limb_tokens(paren_match.group("parens"))

    if re.fullmatch(r"\d+[a-z]?", text):
        return text, []

    # ``1:subparagraph:a:item:i`` already handled; bare ``1(a)`` without colon separator.
    nested = re.match(r"^(\d+[a-z]?)((?:\([^)]+\))+)$", text)
    if nested:
        return nested.group(1).lower(), _split_paren_limb_tokens(nested.group(2))

    return None


def canonical_provision_path(locator: str) -> str:
    """
    Stable provision key shared by SSAFO-style locator format variants.

    Examples (all → ``regulation:5:1:a``):
    ``regulation:5:paragraph:1(a)``, ``…1:subparagraph:a``, ``…1:list:1-a``.
    """
    raw = str(locator or "").strip()
    if not raw or raw == "Multiple provisions":
        return ""
    base = raw.split("|chunk:", 1)[0].strip().lower()
    base = re.sub(r"\s+", " ", base)

    colon = _COLON_PARAGRAPH_PATH_RE.match(base)
    if colon:
        parsed = _limbs_from_paragraph_rest(colon.group("rest"))
        if parsed is None:
            return ""
        para, limbs = parsed
        return ":".join([colon.group("kind").lower(), colon.group("num").lower(), para, *limbs])

    space_sched = _SPACE_SCHEDULE_PARA_RE.match(base)
    if space_sched:
        limbs = _split_paren_limb_tokens(f"({space_sched.group('sub')})") if space_sched.group("sub") else []
        return ":".join(
            [
                space_sched.group("kind").lower(),
                space_sched.group("num").lower(),
                space_sched.group("para").lower(),
                *limbs,
            ]
        )

    space_inst = _SPACE_INSTRUMENT_RE.match(base)
    if space_inst:
        kind = space_inst.group("kind").lower()
        num = space_inst.group("num").lower()
        parens = space_inst.group("parens") or ""
        if not parens:
            return f"{kind}:{num}"
        tokens = _split_paren_limb_tokens(parens)
        # First parenthetical on a regulation/article/rule is the paragraph number.
        if tokens and re.fullmatch(r"\d+[a-z]?", tokens[0]):
            return ":".join([kind, num, *tokens])
        return ":".join([kind, num, *tokens]) if tokens else f"{kind}:{num}"

    return ""


def preferred_locator_label(path: str) -> str:
    """Preferred display locator from a ``canonical_provision_path`` key."""
    parts = [p for p in str(path or "").split(":") if p]
    if len(parts) < 2:
        return ""
    kind, num = parts[0], parts[1]
    if len(parts) == 2:
        return f"{kind}:{num}"
    para = parts[2]
    limbs = parts[3:]
    base = f"{kind}:{num}:paragraph:{para}"
    if not limbs:
        return base
    if len(limbs) == 1:
        return f"{base}:subparagraph:{limbs[0]}"
    if "-" in limbs[1]:
        return f"{base}:subparagraph:{limbs[0]}:items:{limbs[1]}"
    return f"{base}:subparagraph:{limbs[0]}:item:{limbs[1]}"


def _locator_encoding_kind(locator: str) -> str:
    loc = str(locator or "").strip().lower()
    if not loc:
        return _LOCATOR_ENCODING_OTHER
    if ":subparagraph:" in loc or re.search(r":items?:", loc):
        return _LOCATOR_ENCODING_STRUCTURED
    if ":list:" in loc:
        return _LOCATOR_ENCODING_LIST
    if re.search(r"paragraph:\d+[a-z]?[:\s]*\(", loc) or re.search(r":\([a-z0-9]", loc):
        return _LOCATOR_ENCODING_PAREN
    if re.search(r"paragraph\s+\d+[a-z]?\s*\(", loc) or re.search(
        r"\b(?:regulation|schedule|article)\s+\d+[a-z]?\([^)]+\)", loc
    ):
        return _LOCATOR_ENCODING_PAREN
    return _LOCATOR_ENCODING_OTHER


def _normalize_statement_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(text or "").strip())
    return collapsed.lower()


def _statements_list(effective_law_statements: list[dict] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(effective_law_statements, dict):
        rows = effective_law_statements.get("statements")
        return list(rows) if isinstance(rows, list) else []
    return list(effective_law_statements)


def _run_id_from_payload(
    effective_law_statements: list[dict] | dict[str, Any],
) -> str:
    if isinstance(effective_law_statements, dict):
        return str(effective_law_statements.get("run_id") or "run-unknown")
    return "run-unknown"


def _is_direct_candidate(statement: dict[str, Any]) -> bool:
    role = str(statement.get("presentation_role") or "")
    if role != "guidance_matching_candidate" or role in _EXCLUDED_PRESENTATION_ROLES:
        return False
    standalone = str(statement.get("standalone_status") or "")
    return standalone not in _EXCLUDED_STANDALONE_STATUSES


def _risk_flags(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    stmt_by_source_prop: dict[str, dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    standalone = str(statement.get("standalone_status") or "")
    if standalone == "context_dependent":
        flags.append("context_dependent")
    if standalone == "partially_resolved":
        flags.append("partially_resolved")
    if statement.get("warnings"):
        flags.append("has_warnings")
    if str(statement.get("confidence") or "").lower() == "low":
        flags.append("low_confidence")

    has_external_reference = False
    has_malformed_external = False
    for entry in statement.get("required_context") or []:
        if not isinstance(entry, dict):
            continue
        res = str(entry.get("resolution_status") or "")
        if res == "external_reference":
            has_external_reference = True
            if entry.get("malformed"):
                has_malformed_external = True
            continue
        if res == "unresolved":
            flags.append("unresolved_context")
            break
        if res == "missing":
            flags.append("unresolved_context")
            break

    if has_external_reference:
        flags.append("external_reference")
    if has_malformed_external:
        flags.append("malformed_external_reference")

    for entry in statement.get("required_context") or []:
        if not isinstance(entry, dict):
            continue
        res = str(entry.get("resolution_status") or "")
        if res == "external_reference":
            continue
        if res == "ambiguous":
            flags.append("ambiguous_context")
            break

    supporting_ids = list(statement.get("supporting_proposition_ids") or [])
    context_prop_ids: list[str] = []
    for entry in statement.get("required_context") or []:
        if isinstance(entry, dict):
            context_prop_ids.extend(str(pid) for pid in (entry.get("proposition_ids") or []) if pid)

    all_related = list(dict.fromkeys([*supporting_ids, *context_prop_ids]))
    has_definition = False
    has_procedural = False
    for pid in all_related:
        prop = props_by_id.get(pid)
        if prop is not None:
            effect = str(prop.get("legal_effect_type") or "")
            if effect == "definition":
                has_definition = True
            if effect in {"citation", "commencement", "extent", "enforcement", "inspection", "appeal"}:
                has_procedural = True
        related_stmt = stmt_by_source_prop.get(pid)
        if related_stmt is not None:
            role = str(related_stmt.get("presentation_role") or "")
            if role == "supporting_definition":
                has_definition = True
            if role == "procedural_or_enforcement_context":
                has_procedural = True

    if has_definition:
        flags.append("definition_dependency")
    if has_procedural:
        flags.append("procedural_context")

    return list(dict.fromkeys(flags))


def _candidate_status(
    statement: dict[str, Any],
    *,
    risk_flags: list[str],
    evidence: dict[str, Any],
) -> CandidateStatus:
    confidence = str(statement.get("confidence") or "").lower()
    standalone = str(statement.get("standalone_status") or "")
    warnings = list(statement.get("warnings") or [])

    if confidence == "low":
        return "needs_review"
    if "unresolved_context" in risk_flags or "ambiguous_context" in risk_flags:
        return "needs_review"
    if warnings:
        return "needs_review"
    if not evidence.get("source_record_ids"):
        return "needs_review"

    if standalone == "standalone" and confidence in {"high", "medium"}:
        return "ready"
    if standalone in {"partially_resolved", "context_dependent"} and confidence in {"high", "medium"}:
        return "usable_with_context"
    return "needs_review"


def _index_propositions(propositions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(p.get("id") or ""): p for p in propositions if p.get("id")}


def _index_source_inventory(source_inventory: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(source_inventory, dict):
        return {}
    rows = source_inventory.get("rows")
    if isinstance(rows, list):
        return {
            str(row.get("source_record_id") or row.get("id") or ""): row
            for row in rows
            if isinstance(row, dict) and (row.get("source_record_id") or row.get("id"))
        }
    sources = source_inventory.get("sources")
    if isinstance(sources, list):
        return {
            str(row.get("id") or row.get("source_record_id") or ""): row
            for row in sources
            if isinstance(row, dict) and (row.get("id") or row.get("source_record_id"))
        }
    return {}


def _citation_from_source_row(row: dict[str, Any]) -> str:
    return str(row.get("citation") or row.get("title") or "").strip()


def _source_locators(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> set[str]:
    locators: set[str] = set()
    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        locator = normalize_cross_reference_locator(
            str(prop.get("fragment_locator") or prop.get("article_reference") or "")
        )
        if locator:
            locators.add(locator)
    return locators


def _connector_context(statement: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in statement.get("connector_context") or []:
        if isinstance(entry, dict):
            rows.append(dict(entry))
    return rows


def _sanitize_required_context(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop connector-wiring entries mistakenly copied into required_context."""
    supporting_ids = {str(pid) for pid in (statement.get("supporting_proposition_ids") or []) if pid}
    own_locators = _source_locators(statement, props_by_id=props_by_id)
    sanitized: list[dict[str, Any]] = []
    for entry in statement.get("required_context") or []:
        if not isinstance(entry, dict):
            continue
        locator = normalize_cross_reference_locator(str(entry.get("locator") or ""))
        prop_ids = [str(pid) for pid in (entry.get("proposition_ids") or []) if pid]
        kind = str(entry.get("kind") or "")
        if (
            kind in _WIRING_CONTEXT_KINDS
            and prop_ids
            and all(pid in supporting_ids for pid in prop_ids)
        ):
            continue
        if locator and locator in own_locators and prop_ids and all(pid in supporting_ids for pid in prop_ids):
            continue
        sanitized.append(dict(entry))
    return sanitized


def _collect_proposition_ids(statement: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("source_proposition_ids", "supporting_proposition_ids"):
        for pid in statement.get(key) or []:
            if pid and pid not in ids:
                ids.append(str(pid))
    for entry in statement.get("required_context") or []:
        if not isinstance(entry, dict):
            continue
        for pid in entry.get("proposition_ids") or []:
            if pid and pid not in ids:
                ids.append(str(pid))
    for entry in statement.get("connector_context") or []:
        if not isinstance(entry, dict):
            continue
        for key in ("proposition_ids", "via_proposition_ids", "target_proposition_ids"):
            for pid in entry.get(key) or []:
                if pid and pid not in ids:
                    ids.append(str(pid))
    return ids


def _build_evidence(
    proposition_ids: list[str],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_record_ids: list[str] = []
    source_fragment_ids: list[str] = []
    fragment_locators: list[str] = []
    citations: list[str] = []

    for pid in proposition_ids:
        prop = props_by_id.get(pid)
        if not prop:
            continue
        src_id = str(prop.get("source_record_id") or "").strip()
        if src_id and src_id not in source_record_ids:
            source_record_ids.append(src_id)
        frag_id = str(prop.get("source_fragment_id") or "").strip()
        if frag_id and frag_id not in source_fragment_ids:
            source_fragment_ids.append(frag_id)
        locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
        if locator and locator not in fragment_locators:
            fragment_locators.append(locator)

    for src_id in source_record_ids:
        row = sources_by_id.get(src_id)
        if not isinstance(row, dict):
            continue
        citation = _citation_from_source_row(row)
        if citation and citation not in citations:
            citations.append(citation)

    return {
        "source_record_ids": source_record_ids,
        "source_fragment_ids": source_fragment_ids,
        "fragment_locators": fragment_locators,
        "citations": citations,
    }


def _truncate(text: str, max_len: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _presentation_title(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    label = str(statement.get("label") or "").strip()
    if label:
        return label
    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        prop_label = str(prop.get("label") or "").strip()
        if prop_label:
            return prop_label
    text = str(statement.get("statement_text") or "").strip()
    return _truncate(text, _TITLE_TRUNC_LEN) if text else ""


def _presentation_summary(statement: dict[str, Any]) -> str:
    return _truncate(str(statement.get("statement_text") or ""), _SUMMARY_MAX_LEN)


def _presentation_source_label(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> str:
    labels: list[str] = []
    for pid in _collect_proposition_ids(statement):
        prop = props_by_id.get(pid)
        if prop is None:
            continue
        src_id = str(prop.get("source_record_id") or "").strip()
        row = sources_by_id.get(src_id)
        if not isinstance(row, dict):
            continue
        label = _citation_from_source_row(row)
        if label and label not in labels:
            labels.append(label)
    if len(labels) == 1:
        return labels[0]
    if len(labels) > 1:
        return " | ".join(labels)
    return ""


def _presentation_locator_label(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    locators: list[str] = []
    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
        if locator and locator not in locators:
            locators.append(locator)
    if len(locators) == 1:
        return locators[0]
    if len(locators) > 1:
        return "Multiple provisions"
    return ""


def _candidate_id(law_statement_id: str) -> str:
    return f"bcand:{_stable_hash((law_statement_id,))}"


def _prop_locator(prop: dict[str, Any]) -> str:
    return str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()


def _prop_human_label(prop: dict[str, Any]) -> str:
    label = str(prop.get("label") or "").strip()
    if label:
        return label
    text = str(prop.get("proposition_text") or "").strip()
    return _truncate(text, _PROP_LABEL_TRUNC_LEN) if text else ""


def _locators_for_prop_ids(
    prop_ids: list[str],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    locators: list[str] = []
    for pid in prop_ids:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        locator = normalize_cross_reference_locator(_prop_locator(prop))
        if locator and locator not in locators:
            locators.append(locator)
    return locators


def _normalize_extent_token(raw: str) -> list[str]:
    key = str(raw or "").strip().lower()
    if not key:
        return []
    if key in _EXTENT_ALIASES:
        return list(_EXTENT_ALIASES[key])
    norm = normalize_territory_name(raw)
    if norm:
        return [norm]
    return split_territory_list(str(raw))


def _append_territories(values: list[str], additions: list[str]) -> None:
    for item in additions:
        if item and item not in values:
            values.append(item)


def _territories_from_prop(prop: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in ("territorial_application", "extent"):
        raw = prop.get(key)
        if isinstance(raw, list):
            for item in raw:
                _append_territories(found, _normalize_extent_token(str(item or "")))
        elif raw:
            _append_territories(found, _normalize_extent_token(str(raw)))
    return found


def _territories_from_citation_and_title(
    *,
    citation: str,
    title: str,
    kind: str,
) -> list[str]:
    found: list[str] = []
    cite = str(citation or "").strip()
    title_text = str(title or "").strip()
    kind_text = str(kind or "").strip().lower()

    if _CITATION_WSI_RE.search(cite) or kind_text == "wsi" or _TITLE_WALES_RE.search(title_text):
        _append_territories(found, ["Wales"])
    if _CITATION_SSI_RE.search(cite) or kind_text == "ssi" or _TITLE_SCOTLAND_RE.search(title_text):
        _append_territories(found, ["Scotland"])

    if _TITLE_ENGLAND_AND_WALES_RE.search(title_text):
        _append_territories(found, ["England", "Wales"])
    elif _TITLE_ENGLAND_RE.search(title_text):
        _append_territories(found, ["England"])

    return found


def _territories_from_source_row(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    metadata = row.get("metadata")
    meta_dict = metadata if isinstance(metadata, dict) else {}
    _append_territories(found, extent_from_source_metadata(meta_dict))
    _append_territories(
        found,
        _territories_from_citation_and_title(
            citation=_citation_from_source_row(row),
            title=str(row.get("title") or ""),
            kind=str(row.get("kind") or row.get("instrument_type") or ""),
        ),
    )
    return found


def _build_source_territory_cache(propositions: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Aggregate territory labels from all propositions for each source record."""
    by_source: dict[str, list[str]] = {}
    for prop in propositions:
        source_id = str(prop.get("source_record_id") or "").strip()
        if not source_id:
            continue
        territories = _territories_from_prop(prop)
        if not territories:
            continue
        bucket = by_source.setdefault(source_id, [])
        _append_territories(bucket, territories)
    return by_source


def _collect_raw_territory_fields(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    jurisdictions: list[str] = []
    source_jurisdictions: list[str] = []
    extents: list[str] = []
    territorial_applications: list[str] = []

    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        jurisdiction = str(prop.get("jurisdiction") or "").strip()
        if jurisdiction and jurisdiction not in jurisdictions:
            jurisdictions.append(jurisdiction)
        source_jurisdiction = str(prop.get("source_jurisdiction") or "").strip()
        if source_jurisdiction and source_jurisdiction not in source_jurisdictions:
            source_jurisdictions.append(source_jurisdiction)
        for item in prop.get("extent") or []:
            value = str(item or "").strip()
            if value and value not in extents:
                extents.append(value)
        for item in prop.get("territorial_application") or []:
            value = str(item or "").strip()
            if value and value not in territorial_applications:
                territorial_applications.append(value)

    return {
        "jurisdiction": jurisdictions[0] if len(jurisdictions) == 1 else jurisdictions,
        "source_jurisdiction": (
            source_jurisdictions[0] if len(source_jurisdictions) == 1 else source_jurisdictions
        ),
        "extent": extents,
        "territorial_application": territorial_applications,
    }


def _derive_territory_labels(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    source_territory_cache: dict[str, list[str]] | None = None,
) -> list[str]:
    """Conservative UK sub-national territory labels for display and matching."""
    territories: list[str] = []

    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is not None:
            _append_territories(territories, _territories_from_prop(prop))

    source_ids: list[str] = []
    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        src_id = str(prop.get("source_record_id") or "").strip()
        if src_id and src_id not in source_ids:
            source_ids.append(src_id)

    for src_id in source_ids:
        row = sources_by_id.get(src_id)
        if isinstance(row, dict):
            _append_territories(territories, _territories_from_source_row(row))
        cached = (source_territory_cache or {}).get(src_id) or []
        _append_territories(territories, list(cached))

    uk_nations = [t for t in territories if t in _UK_NATION_TERRITORIES]
    if not uk_nations:
        return []

    ordered = [t for t in _UK_NATION_ORDER if t in uk_nations]
    extras = [t for t in uk_nations if t not in ordered]
    return ordered + extras


def _jurisdiction_label_from_territories(territory_labels: list[str]) -> str:
    uk_nations = [t for t in territory_labels if t in _UK_NATION_TERRITORIES]
    if not uk_nations:
        return ""
    if uk_nations == ["England", "Wales"]:
        return "England and Wales"
    if len(uk_nations) == 1:
        return uk_nations[0]
    if len(uk_nations) == 2:
        return f"{uk_nations[0]} and {uk_nations[1]}"
    if len(uk_nations) > 2:
        head = ", ".join(uk_nations[:-1])
        return f"{head}, and {uk_nations[-1]}"
    return ""


def _build_candidate_territory(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    source_territory_cache: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    raw = _collect_raw_territory_fields(statement, props_by_id=props_by_id)
    territory_labels = _derive_territory_labels(
        statement,
        props_by_id=props_by_id,
        sources_by_id=sources_by_id,
        source_territory_cache=source_territory_cache,
    )
    jurisdiction_label = _jurisdiction_label_from_territories(territory_labels)
    return {
        "territory_labels": territory_labels,
        "jurisdiction_label": jurisdiction_label,
        **raw,
    }


def _format_territory_clause(territory: dict[str, Any]) -> str:
    label = str(territory.get("jurisdiction_label") or "").strip()
    if label:
        return f"Territory: {label}."
    return ""


def _format_source_line(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    territory: dict[str, Any],
) -> str:
    citation = _presentation_source_label(
        statement,
        props_by_id=props_by_id,
        sources_by_id=sources_by_id,
    )
    locator = _presentation_locator_label(statement, props_by_id=props_by_id)
    territory_clause = _format_territory_clause(territory)

    parts: list[str] = []
    if citation and locator:
        parts.append(f"{citation}, {locator}")
    elif citation:
        parts.append(citation)
    elif locator:
        parts.append(locator)
    if territory_clause:
        parts.append(territory_clause.rstrip("."))
    line = ". ".join(parts) if parts else ""
    if line and territory_clause:
        return f"{line}."
    return line


def _format_required_context_entry(
    entry: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    raw_locator = str(entry.get("locator") or "").strip()
    resolution = str(entry.get("resolution_status") or "")
    kind = str(entry.get("kind") or "")

    if kind == "chapeau":
        summary = str(entry.get("statement_text") or "").strip()
        if summary and raw_locator:
            return f"chapeau ({raw_locator}): {_truncate(summary, 160)}"
        if summary:
            return f"chapeau: {_truncate(summary, 160)}"
        if raw_locator:
            return f"chapeau: {raw_locator}"
        return "chapeau"

    if resolution == "external_reference" and raw_locator:
        label = "external reference"
        if kind == "external_standard_reference":
            label = "external standard reference"
        elif kind == "external_guidance_reference":
            label = "external guidance reference"
        elif kind == "external_certification_reference":
            label = "external certification reference"
        if entry.get("malformed"):
            return f"{label}: {raw_locator} (may need review)"
        return f"{label}: {raw_locator}"

    locator = normalize_cross_reference_locator(raw_locator)
    prop_ids = [str(pid) for pid in (entry.get("proposition_ids") or []) if pid]
    typed_kind_labels = {
        "applicable_exception": "applicable exception",
        "exception_target": "exception target",
        "trigger_condition": "trigger condition",
    }
    if kind in typed_kind_labels and resolution == "resolved" and prop_ids:
        labels: list[str] = []
        for pid in prop_ids:
            prop = props_by_id.get(pid)
            if prop is None:
                continue
            label = _prop_human_label(prop)
            if label and label not in labels:
                labels.append(label)
        typed_label = typed_kind_labels[kind]
        if labels:
            return f"{typed_label}: {'; '.join(labels)}"
        if locator:
            return f"{typed_label}: {locator}"
        return typed_label

    if not locator:
        return ""

    if resolution == "resolved" and prop_ids:
        labels: list[str] = []
        for pid in prop_ids:
            prop = props_by_id.get(pid)
            if prop is None:
                continue
            label = _prop_human_label(prop)
            if label and label not in labels:
                labels.append(label)
        if labels:
            if len(labels) == 1:
                return f"{locator} ({labels[0]})"
            return f"{locator} ({'; '.join(labels)})"
        return locator

    if resolution == "ambiguous":
        return f"{locator} is ambiguous and may need review"
    if resolution in {"unresolved", "missing"}:
        return f"{locator} is unresolved and may need review"
    if prop_ids:
        locators = _locators_for_prop_ids(prop_ids, props_by_id=props_by_id)
        if locators:
            return f"{locator} ({', '.join(locators)})"
    return locator


def _format_required_context_lines(
    required_context: list[dict[str, Any]],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    hints: list[str] = []
    for entry in required_context:
        if not isinstance(entry, dict):
            continue
        hint = _format_required_context_entry(entry, props_by_id=props_by_id)
        if hint and hint not in hints:
            hints.append(hint)
    return "; ".join(hints)


def _via_locator_from_connector(
    entry: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    for pid in entry.get("via_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        locator = normalize_cross_reference_locator(_prop_locator(prop))
        if locator:
            return locator
    return ""


def _format_connector_context_entry(
    entry: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    kind = str(entry.get("kind") or "")
    locator = normalize_cross_reference_locator(str(entry.get("locator") or ""))
    if not locator:
        return ""

    if kind == "incorporates_context_from":
        via = _via_locator_from_connector(entry, props_by_id=props_by_id)
        if via:
            return f"This rule incorporates context from {locator} via {via}."
        return f"This rule incorporates context from {locator}."

    if kind == "incorporated_elsewhere_by":
        target = normalize_cross_reference_locator(str(entry.get("target_locator") or ""))
        if target:
            return f"This rule is incorporated elsewhere by {locator} (into {target})."
        return f"This rule is incorporated elsewhere by {locator}."

    return ""


def _format_connector_context_lines(
    connector_context: list[dict[str, Any]],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    for entry in connector_context:
        if not isinstance(entry, dict):
            continue
        line = _format_connector_context_entry(entry, props_by_id=props_by_id)
        if line and line not in lines:
            lines.append(line)
    return " ".join(lines)


def _format_tags_line(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
) -> str:
    tags: list[str] = []
    for pid in statement.get("source_proposition_ids") or []:
        prop = props_by_id.get(str(pid))
        if prop is None:
            continue
        effect = str(prop.get("legal_effect_type") or "").strip()
        if effect and effect not in {
            "obligation",
            "prohibition",
            "permission",
            "cross_reference",
        }:
            if effect not in tags:
                tags.append(effect)
        tier = str(prop.get("proposition_tier") or "").strip()
        if tier and tier != "substantive_rule" and tier not in tags:
            tags.append(tier)
    return ", ".join(tags)


def _build_matching_text(
    statement: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    required_context: list[dict[str, Any]],
    connector_context: list[dict[str, Any]],
    territory: dict[str, Any],
) -> str:
    """Assemble deterministic retrieval text from existing candidate fields only."""
    sections: list[str] = []

    title = _presentation_title(statement, props_by_id=props_by_id)
    if title:
        sections.append(f"Title: {title}")

    statement_text = str(statement.get("statement_text") or "").strip()
    if statement_text:
        sections.append(f"Law: {statement_text}")

    source_line = _format_source_line(
        statement,
        props_by_id=props_by_id,
        sources_by_id=sources_by_id,
        territory=territory,
    )
    if source_line:
        sections.append(f"Source: {source_line}")

    context_line = _format_required_context_lines(
        required_context,
        props_by_id=props_by_id,
    )
    if context_line:
        sections.append(f"Context: {context_line}")

    connector_line = _format_connector_context_lines(
        connector_context,
        props_by_id=props_by_id,
    )
    if connector_line:
        sections.append(f"Connector context: {connector_line}")

    tags_line = _format_tags_line(statement, props_by_id=props_by_id)
    if tags_line:
        sections.append(f"Tags: {tags_line}")

    text = "\n".join(sections)
    return _truncate(text, _MATCHING_TEXT_MAX_LEN)


def _normalize_locator_for_dedupe(locator: str) -> str:
    """
    Canonicalize locator strings for same-source duplicate detection.

    Prefer structural provision-path keys so SSAFO-style format variants collide.
    Fall back to cross-ref / whitespace normalisation when the path cannot be parsed.
    """
    raw = str(locator or "").strip()
    if not raw:
        return ""
    path = canonical_provision_path(raw)
    if path:
        return path
    normalized = normalize_cross_reference_locator(raw)
    if normalized and _REGULATION_LOCATOR_KIND_RE.match(normalized):
        return normalized
    text = re.sub(r"\s+", " ", raw.lower())
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(
        r"\b(regulation|schedule|article|paragraph|annex):\s*(\d)",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


_REGULATION_LOCATOR_KIND_RE = re.compile(
    r"^(regulation|schedule|article|paragraph|annex)\s+\d",
    re.IGNORECASE,
)


def _primary_source_record_id(evidence: dict[str, Any]) -> str:
    ids = [str(item).strip() for item in (evidence.get("source_record_ids") or []) if str(item).strip()]
    if len(ids) == 1:
        return ids[0]
    return ""


def _candidate_raw_locator(candidate: dict[str, Any]) -> str:
    raw = str(candidate.get("_raw_locator_label") or "").strip()
    if raw:
        return raw
    presentation = candidate.get("presentation")
    if isinstance(presentation, dict):
        label = str(presentation.get("locator_label") or "").strip()
        if label and label != "Multiple provisions":
            return label
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        locators = [
            str(item).strip()
            for item in (evidence.get("fragment_locators") or [])
            if str(item).strip()
        ]
        if len(locators) == 1:
            return locators[0]
    return ""


def _primary_locator_for_dedupe(candidate: dict[str, Any]) -> str:
    presentation = candidate.get("presentation")
    if isinstance(presentation, dict):
        locator_label = str(presentation.get("locator_label") or "").strip()
        if locator_label and locator_label != "Multiple provisions":
            return _normalize_locator_for_dedupe(locator_label)
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict):
        locators = [
            str(item).strip()
            for item in (evidence.get("fragment_locators") or [])
            if str(item).strip()
        ]
        if len(locators) == 1:
            return _normalize_locator_for_dedupe(locators[0])
    return ""


def _candidate_dedupe_key(candidate: dict[str, Any]) -> str | None:
    """Same-source duplicate key; None when evidence is insufficient to merge safely."""
    source_id = _primary_source_record_id(candidate.get("evidence") or {})
    locator = _primary_locator_for_dedupe(candidate)
    statement = str(candidate.get("normalized_statement_text") or "").strip()
    if not source_id or not locator or not statement:
        return None
    return f"{source_id}|{locator}|{statement}"


def _duplicate_group_id(dedupe_key: str) -> str:
    return f"dupgrp:{_stable_hash((dedupe_key,))}"


def _canonical_candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, str]:
    status = str(candidate.get("candidate_status") or "")
    rank = _CANDIDATE_STATUS_RANK.get(status, 9)
    return (rank, str(candidate.get("id") or ""))


def _altitude_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    encoding = str(candidate.get("_locator_encoding") or _LOCATOR_ENCODING_OTHER)
    enc_rank = _ENCODING_RANK.get(encoding, 9)
    status = str(candidate.get("candidate_status") or "")
    status_rank = _CANDIDATE_STATUS_RANK.get(status, 9)
    return (enc_rank, status_rank, str(candidate.get("id") or ""))


def _is_chapeau_echo(candidate: dict[str, Any], group: list[dict[str, Any]]) -> bool:
    if len(group) < 2:
        return False
    encoding = str(candidate.get("_locator_encoding") or _LOCATOR_ENCODING_OTHER)
    sibling_encodings = {
        str(sibling.get("_locator_encoding") or _LOCATOR_ENCODING_OTHER)
        for sibling in group
        if sibling is not candidate
    }
    if encoding in {_LOCATOR_ENCODING_PAREN, _LOCATOR_ENCODING_LIST} and (
        _LOCATOR_ENCODING_STRUCTURED in sibling_encodings
    ):
        return True

    text = str(candidate.get("statement_text") or "").strip()
    if not _CHAPEAU_STEM_RE.match(text):
        return False
    for sibling in group:
        if sibling is candidate:
            continue
        sibling_text = str(sibling.get("statement_text") or "").strip()
        if sibling_text and not _CHAPEAU_STEM_RE.match(sibling_text):
            return True
    return False


def _fold_chapeau_into_winner(winner: dict[str, Any], echo: dict[str, Any]) -> None:
    raw_locator = _candidate_raw_locator(echo) or str(
        (echo.get("presentation") or {}).get("locator_label") or ""
    ).strip()
    entry: dict[str, Any] = {
        "kind": "chapeau",
        "locator": raw_locator,
        "resolution_status": "resolved",
        "statement_text": str(echo.get("statement_text") or "").strip(),
        "proposition_ids": list(echo.get("source_proposition_ids") or []),
        "resolution_basis": "altitude_collapse",
    }
    context = winner.setdefault("required_context", [])
    if not isinstance(context, list):
        context = []
        winner["required_context"] = context
    context.append(entry)
    _append_chapeau_hint_to_matching_text(winner, entry)

    winner_evidence = winner.get("evidence")
    echo_evidence = echo.get("evidence")
    if isinstance(winner_evidence, dict) and isinstance(echo_evidence, dict):
        for key in ("source_fragment_ids", "fragment_locators"):
            existing = [str(x) for x in (winner_evidence.get(key) or []) if str(x).strip()]
            for item in echo_evidence.get(key) or []:
                value = str(item).strip()
                if value and value not in existing:
                    existing.append(value)
            winner_evidence[key] = existing


def _patch_matching_text_source_locator(candidate: dict[str, Any], *, old_locator: str, new_locator: str) -> None:
    if not old_locator or not new_locator or old_locator == new_locator:
        return
    text = str(candidate.get("matching_text") or "")
    if old_locator in text:
        candidate["matching_text"] = text.replace(old_locator, new_locator, 1)
        candidate["normalized_matching_text"] = _normalize_statement_text(candidate["matching_text"])


def _append_chapeau_hint_to_matching_text(candidate: dict[str, Any], entry: dict[str, Any]) -> None:
    hint = _format_required_context_entry(entry, props_by_id={})
    if not hint:
        return
    text = str(candidate.get("matching_text") or "")
    if hint in text:
        return
    if "\nContext: " in text:
        candidate["matching_text"] = text.replace("\nContext: ", f"\nContext: {hint}; ", 1)
    else:
        candidate["matching_text"] = f"{text}\nContext: {hint}" if text else f"Context: {hint}"
    candidate["normalized_matching_text"] = _normalize_statement_text(candidate["matching_text"])


def _apply_canonical_locator_labels(candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        raw = _candidate_raw_locator(candidate)
        path = canonical_provision_path(raw)
        presentation = candidate.get("presentation")
        if not isinstance(presentation, dict):
            continue
        if path:
            preferred = preferred_locator_label(path)
            old_label = str(presentation.get("locator_label") or "").strip()
            presentation["locator_label"] = preferred
            _patch_matching_text_source_locator(
                candidate,
                old_locator=old_label,
                new_locator=preferred,
            )
        candidate["_provision_path"] = path


def _collapse_chapeau_altitude(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Keep one limb altitude per source+provision path; fold chapeau echoes into context.
    """
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []

    for candidate in candidates:
        source_id = _primary_source_record_id(candidate.get("evidence") or {})
        path = str(candidate.get("_provision_path") or "").strip()
        if not path:
            path = canonical_provision_path(_candidate_raw_locator(candidate))
        if not source_id or not path:
            passthrough.append(candidate)
            continue
        by_key.setdefault((source_id, path), []).append(candidate)

    kept: list[dict[str, Any]] = []
    suppressed = 0
    groups_collapsed = 0

    for group in by_key.values():
        if len(group) == 1:
            kept.append(group[0])
            continue

        echoes = [member for member in group if _is_chapeau_echo(member, group)]
        if not echoes:
            kept.extend(group)
            continue

        non_echoes = [member for member in group if member not in echoes]
        pool = non_echoes if non_echoes else group
        winner = sorted(pool, key=_altitude_sort_key)[0]
        folded_any = False
        for echo in echoes:
            if echo is winner:
                continue
            _fold_chapeau_into_winner(winner, echo)
            suppressed += 1
            folded_any = True
        if folded_any:
            groups_collapsed += 1
        for member in group:
            if member is winner or member not in echoes:
                kept.append(member)

    kept.extend(passthrough)
    return kept, {
        "chapeau_suppressed_count": suppressed,
        "groups_collapsed": groups_collapsed,
    }


def _strip_internal_candidate_fields(candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        candidate.pop("_raw_locator_label", None)
        candidate.pop("_locator_encoding", None)
        candidate.pop("_provision_path", None)


def _attach_same_source_duplicate_metadata(
    candidates: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Soft dedupe (Option B): retain all candidates; mark canonical rows and duplicate groups.

    Cross-source text-equivalent candidates are never grouped.
    """
    by_key: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = _candidate_dedupe_key(candidate)
        if key:
            by_key.setdefault(key, []).append(candidate)

    duplicate_groups = 0
    duplicate_candidates = 0

    for key, group in by_key.items():
        if len(group) < 2:
            continue
        duplicate_groups += 1
        duplicate_candidates += len(group)
        ordered = sorted(group, key=_canonical_candidate_sort_key)
        canonical = ordered[0]
        canonical_id = str(canonical.get("id") or "")
        group_id = _duplicate_group_id(key)
        for member in ordered:
            is_canonical = member is canonical
            member["dedupe"] = {
                "is_canonical": is_canonical,
                "canonical_candidate_id": canonical_id,
                "duplicate_group_id": group_id,
                "duplicate_count": len(group),
                "dedupe_key": key,
            }

    for candidate in candidates:
        if "dedupe" in candidate:
            continue
        candidate_id = str(candidate.get("id") or "")
        key = _candidate_dedupe_key(candidate)
        dedupe: dict[str, Any] = {
            "is_canonical": True,
            "canonical_candidate_id": candidate_id,
            "duplicate_count": 1,
        }
        if key:
            dedupe["dedupe_key"] = key
        candidate["dedupe"] = dedupe

    return {
        "same_source_duplicate_groups": duplicate_groups,
        "same_source_duplicate_candidates": duplicate_candidates,
    }


def build_proposition_matcher_law_candidates(
    *,
    effective_law_statements: list[dict] | dict[str, Any],
    propositions: list[dict],
    proposition_relationships: dict | None = None,
    source_inventory: dict | None = None,
    source_fragments: list[dict] | None = None,
) -> dict[str, Any]:
    """Build Proposition Matcher guidance-matching candidate queue from effective law statements."""
    _ = proposition_relationships
    _ = source_fragments

    statements = _statements_list(effective_law_statements)
    run_id = _run_id_from_payload(effective_law_statements)
    props_by_id = _index_propositions(propositions)
    sources_by_id = _index_source_inventory(source_inventory)
    source_territory_cache = _build_source_territory_cache(propositions)
    stmt_by_source_prop = {
        str(stmt["source_proposition_ids"][0]): stmt
        for stmt in statements
        if stmt.get("source_proposition_ids")
    }

    candidates: list[dict[str, Any]] = []
    for statement in statements:
        if not _is_direct_candidate(statement):
            continue

        law_statement_id = str(statement.get("id") or "")
        statement_text = str(statement.get("statement_text") or "").strip()
        evidence = _build_evidence(
            _collect_proposition_ids(statement),
            props_by_id=props_by_id,
            sources_by_id=sources_by_id,
        )
        risk_flags = _risk_flags(
            statement,
            props_by_id=props_by_id,
            stmt_by_source_prop=stmt_by_source_prop,
        )
        candidate_status = _candidate_status(statement, risk_flags=risk_flags, evidence=evidence)

        required_context = _sanitize_required_context(statement, props_by_id=props_by_id)
        connector_context = _connector_context(statement)
        territory = _build_candidate_territory(
            statement,
            props_by_id=props_by_id,
            sources_by_id=sources_by_id,
            source_territory_cache=source_territory_cache,
        )
        matching_text = _build_matching_text(
            statement,
            props_by_id=props_by_id,
            sources_by_id=sources_by_id,
            required_context=required_context,
            connector_context=connector_context,
            territory=territory,
        )

        candidate: dict[str, Any] = {
            "id": _candidate_id(law_statement_id),
            "law_statement_id": law_statement_id,
            "statement_text": statement_text,
            "normalized_statement_text": _normalize_statement_text(statement_text),
            "matching_text": matching_text,
            "normalized_matching_text": _normalize_statement_text(matching_text),
            "match_role": "primary_law_candidate",
            "candidate_status": candidate_status,
            "risk_flags": risk_flags,
            "confidence": str(statement.get("confidence") or ""),
            "territory_labels": list(territory.get("territory_labels") or []),
            "jurisdiction_label": str(territory.get("jurisdiction_label") or ""),
            "source_proposition_ids": list(statement.get("source_proposition_ids") or []),
            "supporting_proposition_ids": list(statement.get("supporting_proposition_ids") or []),
            "required_context": required_context,
            "connector_context": connector_context,
            "evidence": evidence,
            "presentation": {
                "title": _presentation_title(statement, props_by_id=props_by_id),
                "summary": _presentation_summary(statement),
                "source_label": _presentation_source_label(
                    statement,
                    props_by_id=props_by_id,
                    sources_by_id=sources_by_id,
                ),
                "locator_label": _presentation_locator_label(
                    statement,
                    props_by_id=props_by_id,
                ),
                "territory_labels": list(territory.get("territory_labels") or []),
                "jurisdiction_label": str(territory.get("jurisdiction_label") or ""),
            },
            "provenance": {
                "source": "effective_law_statements",
                "method": "deterministic_beatrice_candidate_export",
            },
        }
        raw_locator = str(candidate["presentation"]["locator_label"] or "").strip()
        candidate["_raw_locator_label"] = raw_locator
        candidate["_locator_encoding"] = _locator_encoding_kind(raw_locator)
        for raw_key in ("jurisdiction", "source_jurisdiction", "extent", "territorial_application"):
            raw_value = territory.get(raw_key)
            if raw_value:
                candidate[raw_key] = raw_value

        candidates.append(candidate)

    _apply_canonical_locator_labels(candidates)
    candidates, altitude_summary = _collapse_chapeau_altitude(candidates)
    candidates.sort(key=lambda row: row["id"])
    duplicate_summary = _attach_same_source_duplicate_metadata(candidates)
    _strip_internal_candidate_fields(candidates)
    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_count": len(candidates),
        "duplicate_summary": duplicate_summary,
        "altitude_summary": altitude_summary,
        "candidates": candidates,
    }
