"""Proposition Matcher-facing proposition export: checkable duties and contextual scope only."""

from __future__ import annotations

from typing import Any, Literal

from law_proposition_extractor_domain import Proposition, resolve_extraction_meta_for_proposition
from law_proposition_extractor_domain.enums import LegalEffectType
from law_proposition_extractor_domain.proposition_notes import EXTRACTION_META_PREFIX

BeatriceRole = Literal["checkable", "contextual_scope", "definition"]

PROPOSITION_MATCHER_CHECKABLE_EFFECTS: frozenset[LegalEffectType] = frozenset(
    {
        LegalEffectType.OBLIGATION,
        LegalEffectType.PROHIBITION,
        LegalEffectType.PERMISSION,
        LegalEffectType.RECORDKEEPING,
        LegalEffectType.NOTIFICATION,
        LegalEffectType.CERTIFICATION,
        LegalEffectType.INSPECTION,
        LegalEffectType.ENFORCEMENT,
        LegalEffectType.APPEAL,
        LegalEffectType.DEROGATION,
    }
)

PROPOSITION_MATCHER_EXCLUDED_BOILERPLATE: frozenset[LegalEffectType] = frozenset(
    {
        LegalEffectType.CITATION,
        LegalEffectType.COMMENCEMENT,
        LegalEffectType.EXTENT,
    }
)

_EXCEPTION_PREFIX = "exception: "


def beatrice_checkable_rows(view: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows Proposition Matcher should treat as checkable guidance duties."""
    return [row for row in view if row.get("beatrice_role") == "checkable"]


def beatrice_contextual_scope_rows(view: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Application-scope rows for territorial/context metadata only."""
    return [row for row in view if row.get("beatrice_role") == "contextual_scope"]


def build_beatrice_proposition_view(
    propositions: list[Proposition],
    *,
    include_definitions: bool = False,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build Proposition Matcher-facing proposition rows from normalised Law Proposition Extractor propositions.

    Default rules:
    - Checkable: ``is_compliance_relevant`` is true and ``legal_effect_type`` is a
      substantive duty type (obligation, prohibition, permission, recordkeeping, etc.).
    - Contextual scope: ``application_scope`` rows for territory metadata, not duties.
    - Definitions: only when ``include_definitions`` or referenced by a checkable row.
    - Excludes citation, commencement, extent, cross-reference, and legacy ``categories``.
    """
    sources = sources_by_id or {}
    ordered = sorted(propositions, key=_sort_key)

    checkable_props = [p for p in ordered if _is_checkable_proposition(p)]
    referenced_definition_ids = _referenced_definition_ids(checkable_props, ordered)

    rows: list[dict[str, Any]] = []
    for prop in ordered:
        role = _beatrice_role(
            prop,
            include_definitions=include_definitions,
            referenced_definition_ids=referenced_definition_ids,
        )
        if role is None:
            continue
        rows.append(_row_from_proposition(prop, role=role, sources=sources))
    return rows


def _sort_key(prop: Proposition) -> tuple[str, str, str]:
    locator = str(prop.fragment_locator or prop.article_reference or "").strip().lower()
    return (str(prop.source_record_id or ""), locator, str(prop.id or ""))


def _is_checkable_proposition(prop: Proposition) -> bool:
    if prop.legal_effect_type in PROPOSITION_MATCHER_EXCLUDED_BOILERPLATE:
        return False
    if prop.legal_effect_type not in PROPOSITION_MATCHER_CHECKABLE_EFFECTS:
        return False
    return prop.is_compliance_relevant is True


def _is_contextual_scope_proposition(prop: Proposition) -> bool:
    return prop.legal_effect_type is LegalEffectType.APPLICATION_SCOPE


def _is_definition_proposition(prop: Proposition) -> bool:
    return prop.legal_effect_type is LegalEffectType.DEFINITION


def _beatrice_role(
    prop: Proposition,
    *,
    include_definitions: bool,
    referenced_definition_ids: set[str],
) -> BeatriceRole | None:
    if _is_contextual_scope_proposition(prop):
        return "contextual_scope"
    if _is_checkable_proposition(prop):
        return "checkable"
    if _is_definition_proposition(prop) and (
        include_definitions or prop.id in referenced_definition_ids
    ):
        return "definition"
    return None


def _referenced_definition_ids(
    checkable: list[Proposition],
    all_props: list[Proposition],
) -> set[str]:
    by_id = {p.id: p for p in all_props}
    definition_ids = {p.id for p in all_props if _is_definition_proposition(p)}
    referenced: set[str] = set()

    locator_tokens: set[str] = set()
    for prop in checkable:
        for target in prop.explicit_cross_reference_targets or []:
            tok = str(target).strip().lower()
            if tok:
                locator_tokens.add(tok)
        for target in prop.cross_reference_targets or []:
            if target in definition_ids:
                referenced.add(target)

    for defn in all_props:
        if not _is_definition_proposition(defn):
            continue
        loc = str(defn.fragment_locator or defn.article_reference or "").strip().lower()
        if loc and loc in locator_tokens:
            referenced.add(defn.id)
        label = str(defn.label or "").strip().lower()
        if label and label in locator_tokens:
            referenced.add(defn.id)

    for prop in checkable:
        for target in prop.cross_reference_targets or []:
            other = by_id.get(target)
            if other is not None and _is_definition_proposition(other):
                referenced.add(target)

    return referenced


def _split_conditions_and_exceptions(
    conditions: list[str],
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    exceptions: list[str] = []
    for item in conditions:
        text = str(item).strip()
        if not text:
            continue
        if text.lower().startswith(_EXCEPTION_PREFIX):
            exceptions.append(text[len(_EXCEPTION_PREFIX) :].strip())
        else:
            kept.append(text)
    return kept, exceptions


def _locator(prop: Proposition) -> str:
    return str(prop.fragment_locator or prop.article_reference or "").strip()


def _source_title(prop: Proposition, sources: dict[str, dict[str, Any]]) -> str:
    src = sources.get(str(prop.source_record_id or ""))
    if not isinstance(src, dict):
        return ""
    return str(src.get("title") or src.get("citation") or "").strip()


def _evidence_fields(prop: Proposition) -> dict[str, Any]:
    meta = (
        resolve_extraction_meta_for_proposition(
            notes=str(prop.notes or ""),
            extraction_debug_meta=prop.extraction_debug_meta,
        )
        or {}
    )
    quote = str(meta.get("evidence_quote") or "").strip()
    trace_id = str(prop.extraction_trace_id or "").strip()
    out: dict[str, Any] = {}
    if quote:
        out["evidence_quote"] = quote
    if trace_id:
        out["extraction_trace_id"] = trace_id
    locator = str(meta.get("evidence_locator") or _locator(prop)).strip()
    if locator:
        out["evidence_locator"] = locator
    return out


def _row_from_proposition(
    prop: Proposition,
    *,
    role: BeatriceRole,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    conditions, exceptions = _split_conditions_and_exceptions(list(prop.conditions or []))
    row: dict[str, Any] = {
        "beatrice_role": role,
        "proposition_id": prop.id,
        "proposition_key": prop.proposition_key,
        "proposition_version_id": prop.proposition_version_id,
        "source_record_id": prop.source_record_id,
        "source_title": _source_title(prop, sources),
        "locator": _locator(prop),
        "proposition_text": prop.proposition_text,
        "label": prop.label,
        "legal_subject": prop.legal_subject,
        "action": prop.action,
        "conditions": conditions,
        "exceptions": exceptions,
        "required_documents": list(prop.required_documents or []),
        "affected_subjects": list(prop.affected_subjects or []),
        "authority": prop.authority,
        "territorial_application": list(prop.territorial_application or []),
        "extent": list(prop.extent or []),
        "proposition_tier": prop.proposition_tier.value,
        "legal_effect_type": prop.legal_effect_type.value,
        "is_compliance_relevant": prop.is_compliance_relevant,
        "is_comparison_anchor": prop.is_comparison_anchor,
    }
    row.update(_evidence_fields(prop))
    if role == "contextual_scope":
        row["is_checkable_for_guidance"] = False
    else:
        row["is_checkable_for_guidance"] = role == "checkable"
    return row


def notes_contain_extraction_meta(notes: str) -> bool:
    """Whether legacy notes still embed law-proposition-extractor extraction meta (Proposition Matcher should not rely on notes)."""
    return EXTRACTION_META_PREFIX in str(notes or "")
