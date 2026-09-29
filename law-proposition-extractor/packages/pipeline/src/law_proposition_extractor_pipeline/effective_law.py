"""Deterministic export transforms for proposition relationships and effective law statements.

Effective-law composition consumes locator edges plus persisted legal rule groups /
typed legal rule relationships (`exception_to`, `triggered_by`).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Sequence

from law_proposition_extractor_domain.proposition_notes import resolve_extraction_meta_for_proposition

from law_proposition_extractor_pipeline.context_locator_resolution import (
    ContextLocatorResolution,
    locator_matches_target,
    normalize_cross_reference_locator as _normalize_cross_reference_locator,
    resolve_context_locator,
    structural_context_for_proposition,
)
from law_proposition_extractor_pipeline.external_reference_classification import (
    external_context_entries_for_proposition,
)

PresentationRole = Literal[
    "guidance_matching_candidate",
    "context_connector",
    "supporting_definition",
    "procedural_or_enforcement_context",
    "debug_only",
]

StandaloneStatus = Literal[
    "standalone",
    "context_dependent",
    "relationship_only",
    "partially_resolved",
    "unresolved_reference",
    "fragmentary",
]

Confidence = Literal["high", "medium", "low"]
ReviewStatus = Literal["accepted", "ambiguous", "unresolved"]
ResolutionStatus = Literal[
    "resolved",
    "ambiguous",
    "unresolved",
    "missing",
    "external_reference",
    "partially_resolved",
]
ContextKind = Literal[
    "host_rule",
    "incorporated_rule",
    "incorporated_factors",
    "supporting_definition",
    "referenced_locator",
    "external_standard_reference",
    "external_guidance_reference",
    "external_certification_reference",
    "applicable_exception",
    "exception_target",
    "trigger_condition",
]

_TYPED_CONTEXT_KINDS = frozenset(
    {
        "applicable_exception",
        "exception_target",
        "trigger_condition",
    }
)

_DIAG_REL_SOURCE_MISSING = "effective_law_relationship_source_missing"
_DIAG_REL_TARGET_MISSING = "effective_law_relationship_target_missing"
_DIAG_REL_GROUP_MISSING = "effective_law_relationship_group_missing"
_DIAG_REL_GROUP_MEMBER_MISSING = "effective_law_relationship_group_member_missing"
_DIAG_REL_SCOPE_MISMATCH = "effective_law_relationship_source_scope_mismatch"

_SCHEMA_VERSION = "1"
_PROVENANCE_FIELD = "explicit_cross_reference_targets"

_REGULATION_LOCATOR_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|paragraph|annex)\s*:?\s*"
    r"(?P<num>\d+[a-z]?)"
    r"(?:\s*\((?P<sub>[^)]+)\))?$",
    re.IGNORECASE,
)

_TEXT_REGULATION_RE = re.compile(
    r"\b(regulation|schedule|article|paragraph|annex)\s+(\d+[a-z]?)(?:\((\d+[a-z]?)\))?",
    re.IGNORECASE,
)

_PROCEDURAL_EFFECTS = frozenset(
    {
        "citation",
        "commencement",
        "extent",
        "enforcement",
        "inspection",
        "appeal",
    }
)

_GUIDANCE_EFFECTS = frozenset(
    {
        "obligation",
        "prohibition",
        "permission",
        "recordkeeping",
        "notification",
        "certification",
        "derogation",
        "application_scope",
        "power",
    }
)


def _stable_hash(parts: tuple[str, ...]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_cross_reference_locator(locator: str | None) -> str:
    """Normalise a cross-reference locator phrase for deterministic matching."""
    return _normalize_cross_reference_locator(locator)


def locator_node_id(source_record_id: str, locator: str) -> str:
    norm = normalize_cross_reference_locator(locator)
    return f"loc:{source_record_id}:{norm}"


def _prop_id(prop: dict[str, Any]) -> str:
    return str(prop.get("id") or "")


def _extraction_meta(prop: dict[str, Any]) -> dict[str, Any]:
    meta = resolve_extraction_meta_for_proposition(
        notes=str(prop.get("notes") or ""),
        extraction_debug_meta=prop.get("extraction_debug_meta"),
    )
    return meta or {}


def _cross_reference_targets(prop: dict[str, Any]) -> list[str]:
    explicit = [
        str(x).strip()
        for x in (prop.get("explicit_cross_reference_targets") or [])
        if str(x).strip()
    ]
    if explicit:
        return explicit
    linked = [
        str(x).strip()
        for x in (prop.get("cross_reference_targets") or [])
        if str(x).strip() and not str(x).strip().startswith("prop:")
    ]
    return linked


def _text_derived_targets(prop: dict[str, Any]) -> list[str]:
    text = str(prop.get("proposition_text") or "")
    found: list[str] = []
    seen: set[str] = set()
    for match in _TEXT_REGULATION_RE.finditer(text):
        kind, num, sub = match.group(1), match.group(2), match.group(3)
        phrase = f"{kind.lower()} {num.lower()}"
        if sub:
            phrase = f"{phrase}({sub.lower()})"
        norm = normalize_cross_reference_locator(phrase)
        if norm and norm not in seen:
            seen.add(norm)
            found.append(norm)
    return found


def _all_reference_targets(prop: dict[str, Any]) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for raw in _cross_reference_targets(prop) + _text_derived_targets(prop):
        norm = normalize_cross_reference_locator(raw)
        if norm and norm not in seen:
            seen.add(norm)
            combined.append(norm)
    return combined


def _locator_parts(locator: str) -> tuple[str, str, str | None] | None:
    norm = normalize_cross_reference_locator(locator)
    match = _REGULATION_LOCATOR_RE.match(norm)
    if not match:
        return None
    kind = match.group("kind").lower()
    num = match.group("num").lower()
    sub = match.group("sub")
    return kind, num, sub.strip().lower() if sub else None


def _is_child_locator_of(parent_locator: str, child_locator: str) -> bool:
    parent_parts = _locator_parts(parent_locator)
    child_parts = _locator_parts(child_locator)
    if parent_parts is None or child_parts is None:
        return False
    parent_kind, parent_num, parent_sub = parent_parts
    child_kind, child_num, child_sub = child_parts
    return (
        parent_sub is None
        and child_sub is not None
        and parent_kind == child_kind
        and parent_num == child_num
    )


def _has_more_specific_target(target: str, all_targets: list[str]) -> bool:
    return any(_is_child_locator_of(target, other) for other in all_targets if other != target)


def prune_subsumed_locators(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop broad parent locators when a resolved child locator is present."""
    pruned: list[dict[str, Any]] = []
    for entry in entries:
        locator = str(entry.get("locator") or "")
        parts = _locator_parts(locator)
        if parts is not None and parts[2] is None:
            has_resolved_child = any(
                _is_child_locator_of(locator, other["locator"])
                and other.get("resolution_status") == "resolved"
                for other in entries
                if other is not entry
            )
            if has_resolved_child:
                continue
        pruned.append(entry)
    return pruned


def _filter_self_reference_context(
    source_prop_id: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Omit locators that resolve only to the source connector proposition."""
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        matched = list(entry.get("proposition_ids") or [])
        if matched == [source_prop_id]:
            continue
        filtered.append(entry)
    return filtered


_HOST_CUES = (
    "under",
    "for the purposes of",
    "in paragraph",
    "in regulation",
)

_INCORPORATED_CUES = (
    "specified in",
    "set out in",
    "listed in",
    "mentioned in",
    "provided by",
    "subject to",
)


def _classify_locator_kind_from_text(text: str, target: str) -> ContextKind | None:
    """Classify a locator's role from surrounding cross-reference phrasing."""
    target_norm = normalize_cross_reference_locator(target)
    text_lower = text.lower()
    for match in _TEXT_REGULATION_RE.finditer(text):
        kind, num, sub = match.group(1), match.group(2), match.group(3)
        phrase = f"{kind.lower()} {num.lower()}"
        if sub:
            phrase = f"{phrase}({sub.lower()})"
        if normalize_cross_reference_locator(phrase) != target_norm:
            continue
        before = text_lower[: match.start()].rstrip()
        for cue in _INCORPORATED_CUES:
            if before.endswith(cue):
                if "factor" in text_lower:
                    return "incorporated_factors"
                return "incorporated_rule"
        for cue in _HOST_CUES:
            if before.endswith(cue):
                return "host_rule"
    return None


def _locator_matches_target(prop_locator: str, target_locator: str) -> bool:
    return locator_matches_target(prop_locator, target_locator)


def _build_locator_index(
    propositions: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """source_record_id -> normalised target -> matching proposition ids (same source only)."""
    index: dict[str, dict[str, list[str]]] = {}
    for prop in propositions:
        source_id = str(prop.get("source_record_id") or "").strip()
        prop_id = _prop_id(prop)
        if not source_id or not prop_id:
            continue
        locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
        if not locator:
            continue
        bucket = index.setdefault(source_id, {})
        for target in _all_reference_targets(prop):
            if _locator_matches_target(locator, target):
                bucket.setdefault(target, []).append(prop_id)
        norm_loc = normalize_cross_reference_locator(locator)
        if norm_loc:
            bucket.setdefault(norm_loc, [])
            if prop_id not in bucket[norm_loc]:
                bucket[norm_loc].append(prop_id)
    return index


def _resolution_to_review_status(
    resolution: ContextLocatorResolution,
) -> tuple[ReviewStatus, ResolutionStatus, list[str], str | None]:
    basis = getattr(resolution, "resolution_basis", None)
    if resolution.review_status == "accepted":
        res_status: ResolutionStatus = resolution.resolution_status  # type: ignore[assignment]
        if res_status not in {"resolved", "partially_resolved"}:
            res_status = "resolved"
        return "accepted", res_status, resolution.proposition_ids, basis
    if resolution.review_status == "ambiguous":
        return "ambiguous", "ambiguous", resolution.proposition_ids, basis
    return "unresolved", "unresolved", resolution.proposition_ids, basis


def _legacy_resolve_locator_in_source(
    *,
    source_record_id: str,
    target_locator: str,
    propositions: list[dict[str, Any]],
    locator_index: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[ReviewStatus, list[str]]:
    """Proposition-index-only fallback when source fragments are unavailable."""
    index = locator_index if locator_index is not None else _build_locator_index(propositions)
    source_bucket = index.get(source_record_id, {})
    target_norm = normalize_cross_reference_locator(target_locator)

    exact = list(dict.fromkeys(source_bucket.get(target_norm, [])))
    if len(exact) == 1:
        return "accepted", exact
    if len(exact) > 1:
        return "ambiguous", exact

    matches: list[str] = []
    for prop in propositions:
        if str(prop.get("source_record_id") or "") != source_record_id:
            continue
        prop_id = _prop_id(prop)
        locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "")
        if prop_id and _locator_matches_target(locator, target_norm):
            matches.append(prop_id)
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return "accepted", unique
    if len(unique) > 1:
        return "ambiguous", unique
    return "unresolved", []


def resolve_locator_in_source(
    *,
    source_record_id: str,
    target_locator: str,
    propositions: list[dict[str, Any]],
    source_fragments: list[dict[str, Any]] | None = None,
    structural_context: Any | None = None,
    locator_index: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[ReviewStatus, list[str]]:
    """Resolve a locator to proposition ids within the same source record."""
    if source_fragments:
        resolution = resolve_context_locator(
            target_locator,
            source_record_id=source_record_id,
            source_fragments=source_fragments,
            structural_context=structural_context,
            propositions=propositions,
        )
        review_status, _, prop_ids, _basis = _resolution_to_review_status(resolution)
        return review_status, prop_ids
    return _legacy_resolve_locator_in_source(
        source_record_id=source_record_id,
        target_locator=target_locator,
        propositions=propositions,
        locator_index=locator_index,
    )


def resolve_locator_in_source_detailed(
    *,
    source_record_id: str,
    target_locator: str,
    propositions: list[dict[str, Any]],
    source_fragments: list[dict[str, Any]] | None = None,
    structural_context: Any | None = None,
    locator_index: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[ReviewStatus, ResolutionStatus, list[str], str | None]:
    """Resolve a locator with export resolution_status semantics."""
    if source_fragments:
        resolution = resolve_context_locator(
            target_locator,
            source_record_id=source_record_id,
            source_fragments=source_fragments,
            structural_context=structural_context,
            propositions=propositions,
        )
        return _resolution_to_review_status(resolution)

    review_status, prop_ids = _legacy_resolve_locator_in_source(
        source_record_id=source_record_id,
        target_locator=target_locator,
        propositions=propositions,
        locator_index=locator_index,
    )
    if review_status == "accepted":
        return review_status, "resolved", prop_ids, "explicit"
    if review_status == "ambiguous":
        return review_status, "ambiguous", prop_ids, "instrument_wide"
    return review_status, "unresolved", prop_ids, "unresolved"


def classify_presentation_role(prop: dict[str, Any]) -> PresentationRole:
    effect = str(prop.get("legal_effect_type") or "").strip()
    tier = str(prop.get("proposition_tier") or "").strip()

    if effect == "cross_reference" or tier == "relationship_reference":
        return "context_connector"
    if effect == "definition" or tier == "definitional_rule":
        return "supporting_definition"
    if effect in _PROCEDURAL_EFFECTS:
        return "procedural_or_enforcement_context"
    if effect in _GUIDANCE_EFFECTS and prop.get("is_compliance_relevant") is True:
        return "guidance_matching_candidate"
    if effect in _GUIDANCE_EFFECTS:
        return "guidance_matching_candidate"
    if tier in {"substantive_rule", "scope_rule", "procedural_rule"}:
        return "guidance_matching_candidate"
    return "debug_only"


def classify_standalone_status(
    prop: dict[str, Any],
    *,
    resolution_statuses: list[ResolutionStatus] | None = None,
) -> StandaloneStatus:
    effect = str(prop.get("legal_effect_type") or "").strip()
    tier = str(prop.get("proposition_tier") or "").strip()

    if effect == "cross_reference" or tier == "relationship_reference":
        if resolution_statuses:
            if any(status == "resolved" for status in resolution_statuses):
                if any(status in {"ambiguous", "unresolved", "missing"} for status in resolution_statuses):
                    return "partially_resolved"
                return "relationship_only"
            if any(status == "ambiguous" for status in resolution_statuses):
                return "partially_resolved"
            return "unresolved_reference"
        return "relationship_only"

    completeness = str(_extraction_meta(prop).get("completeness_status") or "").strip()
    if completeness == "context_dependent":
        return "context_dependent"
    if completeness == "fragmentary":
        return "fragmentary"

    internal_unresolved = {
        status
        for status in (resolution_statuses or [])
        if status in {"ambiguous", "unresolved", "missing", "partially_resolved"}
    }
    if internal_unresolved:
        return "partially_resolved"

    return "standalone"


def classify_confidence(prop: dict[str, Any], *, standalone_status: StandaloneStatus) -> Confidence:
    if standalone_status in {"unresolved_reference", "fragmentary"}:
        return "low"
    if standalone_status in {"partially_resolved", "context_dependent", "relationship_only"}:
        return "medium"
    meta_conf = str(_extraction_meta(prop).get("model_confidence") or "").strip().lower()
    if meta_conf in {"high", "medium", "low"}:
        return meta_conf  # type: ignore[return-value]
    return "high"


def _warnings_for_required_context(required_context: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for entry in required_context:
        target = str(entry["locator"])
        res_status = entry["resolution_status"]
        if res_status == "external_reference":
            if entry.get("malformed"):
                warnings.append(f"malformed external reference: {target}")
            continue
        if res_status == "ambiguous":
            warnings.append(f"ambiguous locator resolution for {target}")
        elif res_status == "unresolved":
            warnings.append(f"unresolved locator reference: {target}")
    return warnings


def _context_kind_for_target(target: str, prop: dict[str, Any]) -> ContextKind:
    effect = str(prop.get("legal_effect_type") or "")
    text = str(prop.get("proposition_text") or "")
    if effect == "definition":
        return "supporting_definition"
    from_text = _classify_locator_kind_from_text(text, target)
    if from_text is not None:
        return from_text
    text_lower = text.lower()
    if "factor" in text_lower:
        return "incorporated_factors"
    parts = _locator_parts(target)
    if parts is not None and parts[2] is None:
        return "referenced_locator"
    return "incorporated_rule"


def _edge_id(edge_type: str, from_id: str, to_id: str, evidence: str) -> str:
    return f"prel:{_stable_hash((edge_type, from_id, to_id, evidence))}"


def _statement_id(source_ids: list[str], presentation_role: str) -> str:
    return f"lawstmt:{_stable_hash((','.join(sorted(source_ids)), presentation_role))}"


def _strip_field(value: Any) -> str:
    return str(value or "").strip()


def _groups_by_id(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("groups")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        group_id = _strip_field(row.get("id"))
        if group_id:
            out[group_id] = row
    return out


def _typed_relationships(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("relationships")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _composition_diagnostic(
    code: str,
    *,
    relationship_id: str | None = None,
    relationship_type: str | None = None,
    source_id: str | None = None,
    target_id: str | None = None,
    legal_rule_group_id: str | None = None,
    member_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code}
    if relationship_id:
        row["relationship_id"] = relationship_id
    if relationship_type:
        row["relationship_type"] = relationship_type
    if source_id:
        row["source_id"] = source_id
    if target_id:
        row["target_id"] = target_id
    if legal_rule_group_id:
        row["legal_rule_group_id"] = legal_rule_group_id
    if member_id:
        row["member_id"] = member_id
    if detail:
        row["detail"] = detail
    return row


def _prop_locator_for_context(prop: dict[str, Any]) -> str:
    return _strip_field(prop.get("fragment_locator") or prop.get("article_reference"))


def _typed_context_entry(
    *,
    kind: ContextKind,
    context_prop: dict[str, Any],
    relationship: dict[str, Any],
    relationship_direction: str,
    inherited_via_group: bool,
    legal_rule_group_id: str | None,
) -> dict[str, Any]:
    locator = (
        _prop_locator_for_context(context_prop)
        or _strip_field(relationship.get("target_canonical_locator"))
        or _strip_field(relationship.get("referenced_locator"))
    )
    entry: dict[str, Any] = {
        "kind": kind,
        "locator": locator,
        "resolution_status": "resolved",
        "proposition_ids": [_prop_id(context_prop)],
        "relationship_id": _strip_field(relationship.get("id")),
        "relationship_type": _strip_field(relationship.get("relationship_type")),
        "relationship_direction": relationship_direction,
        "inherited_via_group": bool(inherited_via_group),
    }
    if legal_rule_group_id:
        entry["legal_rule_group_id"] = legal_rule_group_id
    for field in (
        "resolution_basis",
        "inference_basis",
        "referenced_locator",
        "reference_text",
        "source_fragment_id",
        "target_source_fragment_id",
        "target_canonical_locator",
    ):
        value = relationship.get(field)
        if value is not None and _strip_field(value):
            entry[field] = value
    return entry


def _expand_relationship_endpoint(
    relationship: dict[str, Any],
    *,
    props_by_id: dict[str, dict[str, Any]],
    groups_by_id: dict[str, dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], bool, str | None]]:
    """Expand a typed relationship target to retained propositions (one edge deep)."""
    rel_id = _strip_field(relationship.get("id"))
    rel_type = _strip_field(relationship.get("relationship_type"))
    target_kind = _strip_field(relationship.get("target_kind"))
    target_id = _strip_field(relationship.get("target_id"))
    source_record_id = _strip_field(relationship.get("source_record_id"))
    source_snapshot_id = _strip_field(relationship.get("source_snapshot_id"))

    if target_kind == "proposition":
        target_prop = props_by_id.get(target_id)
        if target_prop is None:
            diagnostics.append(
                _composition_diagnostic(
                    _DIAG_REL_TARGET_MISSING,
                    relationship_id=rel_id or None,
                    relationship_type=rel_type or None,
                    target_id=target_id or None,
                )
            )
            return []
        target_record = _strip_field(
            target_prop.get("source_record_id") or target_prop.get("source_document_id")
        )
        target_snapshot = _strip_field(target_prop.get("source_snapshot_id"))
        if (
            source_record_id
            and target_record
            and source_record_id != target_record
        ) or (
            source_snapshot_id
            and target_snapshot
            and source_snapshot_id != target_snapshot
        ):
            diagnostics.append(
                _composition_diagnostic(
                    _DIAG_REL_SCOPE_MISMATCH,
                    relationship_id=rel_id or None,
                    relationship_type=rel_type or None,
                    source_id=_strip_field(relationship.get("source_id")) or None,
                    target_id=target_id or None,
                    detail="target proposition source/snapshot does not match relationship scope",
                )
            )
            return []
        return [(target_prop, False, None)]

    if target_kind != "legal_rule_group":
        return []

    group = groups_by_id.get(target_id)
    if group is None:
        diagnostics.append(
            _composition_diagnostic(
                _DIAG_REL_GROUP_MISSING,
                relationship_id=rel_id or None,
                relationship_type=rel_type or None,
                target_id=target_id or None,
                legal_rule_group_id=target_id or None,
            )
        )
        return []

    group_record = _strip_field(group.get("source_record_id"))
    group_snapshot = _strip_field(group.get("source_snapshot_id"))
    if (
        source_record_id
        and group_record
        and source_record_id != group_record
    ) or (
        source_snapshot_id
        and group_snapshot
        and source_snapshot_id != group_snapshot
    ):
        diagnostics.append(
            _composition_diagnostic(
                _DIAG_REL_SCOPE_MISMATCH,
                relationship_id=rel_id or None,
                relationship_type=rel_type or None,
                source_id=_strip_field(relationship.get("source_id")) or None,
                target_id=target_id or None,
                legal_rule_group_id=target_id or None,
                detail="legal rule group source/snapshot does not match relationship scope",
            )
        )
        return []

    member_ids = [
        _strip_field(mid)
        for mid in (group.get("member_proposition_ids") or [])
        if _strip_field(mid)
    ]
    expanded: list[tuple[dict[str, Any], bool, str | None]] = []
    for member_id in member_ids:
        member = props_by_id.get(member_id)
        if member is None:
            diagnostics.append(
                _composition_diagnostic(
                    _DIAG_REL_GROUP_MEMBER_MISSING,
                    relationship_id=rel_id or None,
                    relationship_type=rel_type or None,
                    legal_rule_group_id=target_id or None,
                    member_id=member_id,
                )
            )
            continue
        expanded.append((member, True, target_id))
    return expanded


def _collect_typed_required_contexts(
    propositions: list[dict[str, Any]],
    *,
    legal_rule_groups: dict[str, Any] | None,
    legal_rule_relationships: dict[str, Any] | None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build per-proposition typed required_context entries from persisted relationships."""
    props_by_id = {_prop_id(p): p for p in propositions if _prop_id(p)}
    groups_by_id = _groups_by_id(legal_rule_groups)
    relationships = _typed_relationships(legal_rule_relationships)
    if not relationships:
        return {}, [], []

    typed_by_prop: dict[str, list[dict[str, Any]]] = {}
    seen_keys: set[tuple[str, str, str, str]] = set()
    diagnostics: list[dict[str, Any]] = []
    decision_facts: list[dict[str, Any]] = []
    seen_fact_keys: set[tuple[str, ...]] = set()

    for relationship in relationships:
        rel_id = _strip_field(relationship.get("id"))
        rel_type = _strip_field(relationship.get("relationship_type"))
        source_id = _strip_field(relationship.get("source_id"))
        if not source_id or not rel_type:
            continue

        source_prop = props_by_id.get(source_id)
        if source_prop is None:
            diagnostics.append(
                _composition_diagnostic(
                    _DIAG_REL_SOURCE_MISSING,
                    relationship_id=rel_id or None,
                    relationship_type=rel_type or None,
                    source_id=source_id,
                )
            )
            continue

        source_record = _strip_field(
            source_prop.get("source_record_id") or source_prop.get("source_document_id")
        )
        source_snapshot = _strip_field(source_prop.get("source_snapshot_id"))
        rel_record = _strip_field(relationship.get("source_record_id"))
        rel_snapshot = _strip_field(relationship.get("source_snapshot_id"))
        if (
            rel_record
            and source_record
            and rel_record != source_record
        ) or (
            rel_snapshot
            and source_snapshot
            and rel_snapshot != source_snapshot
        ):
            diagnostics.append(
                _composition_diagnostic(
                    _DIAG_REL_SCOPE_MISMATCH,
                    relationship_id=rel_id or None,
                    relationship_type=rel_type or None,
                    source_id=source_id,
                    detail="source proposition source/snapshot does not match relationship scope",
                )
            )
            continue

        endpoints = _expand_relationship_endpoint(
            relationship,
            props_by_id=props_by_id,
            groups_by_id=groups_by_id,
            diagnostics=diagnostics,
        )
        if not endpoints:
            continue

        target_kind = _strip_field(relationship.get("target_kind"))
        target_id = _strip_field(relationship.get("target_id"))
        ordered_group_members: list[str] = []
        if target_kind == "legal_rule_group" and target_id:
            group = groups_by_id.get(target_id) or {}
            ordered_group_members = [
                _strip_field(mid)
                for mid in (group.get("member_proposition_ids") or [])
                if _strip_field(mid)
            ]

        def _append(owner_id: str, entry: dict[str, Any]) -> bool:
            key = (
                owner_id,
                str(entry.get("kind") or ""),
                str(entry.get("relationship_id") or ""),
                ",".join(entry.get("proposition_ids") or []),
            )
            if key in seen_keys:
                return False
            seen_keys.add(key)
            typed_by_prop.setdefault(owner_id, []).append(entry)
            return True

        def _record_attach(
            *,
            fact_kind: str,
            receiving_proposition_id: str,
            context_kind: str,
            context_prop: dict[str, Any],
            via_group: bool,
            group_id: str | None,
            expansion_direction: str,
            role_assignment_basis: str,
        ) -> None:
            context_prop_id = _prop_id(context_prop)
            fact_key = (
                fact_kind,
                receiving_proposition_id,
                context_kind,
                context_prop_id,
                rel_id,
                group_id or "",
            )
            if fact_key in seen_fact_keys:
                return
            seen_fact_keys.add(fact_key)
            decision_facts.append(
                {
                    "fact_kind": fact_kind,
                    "receiving_proposition_id": receiving_proposition_id,
                    "context_kind": context_kind,
                    "context_proposition_id": context_prop_id,
                    "context_proposition_locator": _prop_locator_for_context(context_prop),
                    "legal_rule_relationship_id": rel_id,
                    "relationship_type": rel_type,
                    "relationship_source_proposition_id": source_id,
                    "relationship_target_kind": target_kind,
                    "relationship_target_id": target_id,
                    "legal_rule_group_id": group_id,
                    "ordered_group_members": list(ordered_group_members),
                    "inherited_via_group": bool(via_group),
                    "expansion_direction": expansion_direction,
                    "role_assignment_basis": role_assignment_basis,
                    "source_record_id": source_record or rel_record,
                    "source_snapshot_id": source_snapshot or rel_snapshot,
                }
            )

        if rel_type == "exception_to":
            for endpoint_prop, via_group, group_id in endpoints:
                endpoint_id = _prop_id(endpoint_prop)
                if not endpoint_id or endpoint_id == source_id:
                    continue
                applicable = _typed_context_entry(
                    kind="applicable_exception",
                    context_prop=source_prop,
                    relationship=relationship,
                    relationship_direction="incoming",
                    inherited_via_group=via_group,
                    legal_rule_group_id=group_id,
                )
                if _append(endpoint_id, applicable):
                    _record_attach(
                        fact_kind="attach_applicable_exception",
                        receiving_proposition_id=endpoint_id,
                        context_kind="applicable_exception",
                        context_prop=source_prop,
                        via_group=via_group,
                        group_id=group_id,
                        expansion_direction="bidirectional_exception_projection",
                        role_assignment_basis=(
                            "exception_to_group_expansion"
                            if via_group
                            else "exception_to_direct_proposition"
                        ),
                    )
                exception_target = _typed_context_entry(
                    kind="exception_target",
                    context_prop=endpoint_prop,
                    relationship=relationship,
                    relationship_direction="outgoing",
                    inherited_via_group=via_group,
                    legal_rule_group_id=group_id,
                )
                if _append(source_id, exception_target):
                    _record_attach(
                        fact_kind="attach_exception_target",
                        receiving_proposition_id=source_id,
                        context_kind="exception_target",
                        context_prop=endpoint_prop,
                        via_group=via_group,
                        group_id=group_id,
                        expansion_direction="bidirectional_exception_projection",
                        role_assignment_basis=(
                            "exception_to_group_expansion"
                            if via_group
                            else "exception_to_direct_proposition"
                        ),
                    )
        elif rel_type == "triggered_by":
            for endpoint_prop, via_group, group_id in endpoints:
                endpoint_id = _prop_id(endpoint_prop)
                if not endpoint_id or endpoint_id == source_id:
                    continue
                trigger = _typed_context_entry(
                    kind="trigger_condition",
                    context_prop=endpoint_prop,
                    relationship=relationship,
                    relationship_direction="outgoing",
                    inherited_via_group=via_group,
                    legal_rule_group_id=group_id,
                )
                if _append(source_id, trigger):
                    _record_attach(
                        fact_kind="attach_trigger_condition",
                        receiving_proposition_id=source_id,
                        context_kind="trigger_condition",
                        context_prop=endpoint_prop,
                        via_group=via_group,
                        group_id=group_id,
                        expansion_direction="source_only",
                        role_assignment_basis=(
                            "triggered_by_group_expansion_source_only"
                            if via_group
                            else "triggered_by_direct_proposition_source_only"
                        ),
                    )

    def _context_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        context_ids = [str(pid) for pid in (row.get("proposition_ids") or []) if pid]
        context_id = context_ids[0] if context_ids else ""
        context_prop = props_by_id.get(context_id) or {}
        source_order = context_prop.get("source_order")
        try:
            order_key: tuple[Any, ...] = (0, int(source_order))
        except (TypeError, ValueError):
            order_key = (1, 0)
        return (
            _strip_field(row.get("kind")),
            order_key,
            context_id,
            _strip_field(row.get("relationship_id")),
            _strip_field(row.get("locator")),
        )

    # Deterministic per-proposition ordering: kind, context source_order, ids.
    for owner_id, entries in typed_by_prop.items():
        entries.sort(key=_context_sort_key)
        typed_by_prop[owner_id] = entries

    diag_keys: set[tuple[str, ...]] = set()
    ordered_diags: list[dict[str, Any]] = []
    for row in sorted(
        diagnostics,
        key=lambda d: (
            _strip_field(d.get("code")),
            _strip_field(d.get("relationship_id")),
            _strip_field(d.get("source_id")),
            _strip_field(d.get("target_id")),
            _strip_field(d.get("member_id")),
            _strip_field(d.get("detail")),
        ),
    ):
        key = (
            _strip_field(row.get("code")),
            _strip_field(row.get("relationship_id")),
            _strip_field(row.get("source_id")),
            _strip_field(row.get("target_id")),
            _strip_field(row.get("member_id")),
            _strip_field(row.get("detail")),
        )
        if key in diag_keys:
            continue
        diag_keys.add(key)
        ordered_diags.append(row)

    decision_facts.sort(
        key=lambda row: (
            str(row.get("fact_kind") or ""),
            str(row.get("receiving_proposition_id") or ""),
            str(row.get("context_kind") or ""),
            str(row.get("context_proposition_id") or ""),
            str(row.get("legal_rule_relationship_id") or ""),
            str(row.get("legal_rule_group_id") or ""),
        )
    )
    return typed_by_prop, ordered_diags, decision_facts


def _typed_proposition_ids(entries: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for entry in entries:
        if str(entry.get("kind") or "") not in _TYPED_CONTEXT_KINDS:
            continue
        for pid in entry.get("proposition_ids") or []:
            text = _strip_field(pid)
            if text:
                covered.add(text)
    return covered


def _covering_typed_entry(
    *,
    typed_entries: list[dict[str, Any]],
    covered_prop_ids: Sequence[str],
) -> dict[str, Any] | None:
    covered = {_strip_field(pid) for pid in covered_prop_ids if _strip_field(pid)}
    if not covered:
        return None
    for entry in typed_entries:
        kind = str(entry.get("kind") or "")
        if kind not in _TYPED_CONTEXT_KINDS:
            continue
        entry_ids = {
            _strip_field(pid) for pid in (entry.get("proposition_ids") or []) if _strip_field(pid)
        }
        if entry_ids & covered:
            return entry
    return None


def _dedupe_locator_context_against_typed(
    locator_entries: list[dict[str, Any]],
    *,
    typed_prop_ids: set[str],
    typed_entries: list[dict[str, Any]] | None = None,
    receiving_proposition_id: str | None = None,
    decision_facts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Prefer typed relationship context over generic locator duplicates."""
    if not typed_prop_ids:
        return locator_entries
    typed_rows = typed_entries or []
    deduped: list[dict[str, Any]] = []
    for entry in locator_entries:
        kind = str(entry.get("kind") or "")
        if kind in _TYPED_CONTEXT_KINDS:
            deduped.append(entry)
            continue
        if str(entry.get("resolution_status") or "") == "external_reference":
            deduped.append(entry)
            continue
        prop_ids = [_strip_field(pid) for pid in (entry.get("proposition_ids") or []) if _strip_field(pid)]
        if not prop_ids:
            deduped.append(entry)
            continue
        remaining = [pid for pid in prop_ids if pid not in typed_prop_ids]
        if not remaining:
            # Fully covered by typed context — suppress generic duplicate.
            if decision_facts is not None and receiving_proposition_id:
                covering = _covering_typed_entry(
                    typed_entries=typed_rows,
                    covered_prop_ids=prop_ids,
                )
                if covering is not None:
                    decision_facts.append(
                        {
                            "fact_kind": "prefer_typed_context_over_generic_locator",
                            "receiving_proposition_id": receiving_proposition_id,
                            "generic_locator": _strip_field(entry.get("locator")),
                            "generic_context_kind": kind,
                            "generic_target_proposition_ids": list(prop_ids),
                            "typed_relationship_id": _strip_field(
                                covering.get("relationship_id")
                            ),
                            "typed_context_kind": _strip_field(covering.get("kind")),
                            "equivalence_reason": (
                                "generic_locator_targets_already_covered_by_typed_context"
                            ),
                        }
                    )
            continue
        if remaining != prop_ids:
            updated = dict(entry)
            updated["proposition_ids"] = remaining
            deduped.append(updated)
            continue
        deduped.append(entry)
    return deduped


def build_proposition_relationships(
    propositions: list[dict[str, Any]],
    *,
    run_id: str,
    source_fragments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build deterministic proposition/locator relationship edges."""
    locator_index = _build_locator_index(propositions)
    edges: list[dict[str, Any]] = []
    seen_edge_ids: set[str] = set()

    for prop in propositions:
        prop_id = _prop_id(prop)
        source_id = str(prop.get("source_record_id") or "").strip()
        if not prop_id or not source_id:
            continue

        targets = _all_reference_targets(prop)
        if not targets and str(prop.get("legal_effect_type") or "") != "cross_reference":
            continue

        provenance_field = _PROVENANCE_FIELD
        if not prop.get("explicit_cross_reference_targets") and prop.get("cross_reference_targets"):
            provenance_field = "cross_reference_targets"

        for target in targets:
            loc_id = locator_node_id(source_id, target)
            text_edge = {
                "id": _edge_id("text_references_locator", prop_id, loc_id, target),
                "type": "text_references_locator",
                "from": prop_id,
                "to": loc_id,
                "source_record_id": source_id,
                "confidence": "medium",
                "method": "deterministic_locator_parse",
                "review_status": "accepted",
                "locator_specificity": (
                    "broad" if _has_more_specific_target(target, targets) else "specific"
                ),
                "evidence": [target],
                "provenance": {
                    "artefact": "propositions.json",
                    "field": provenance_field,
                },
            }
            if text_edge["id"] not in seen_edge_ids:
                seen_edge_ids.add(text_edge["id"])
                edges.append(text_edge)

            review_status, matched_ids = resolve_locator_in_source(
                source_record_id=source_id,
                target_locator=target,
                propositions=propositions,
                source_fragments=source_fragments,
                structural_context=structural_context_for_proposition(
                    prop,
                    source_fragments=source_fragments,
                ),
                locator_index=locator_index,
            )
            if not matched_ids:
                continue
            for matched_id in matched_ids:
                resolve_edge = {
                    "id": _edge_id("locator_resolves_to", loc_id, matched_id, target),
                    "type": "locator_resolves_to",
                    "from": loc_id,
                    "to": matched_id,
                    "source_record_id": source_id,
                    "confidence": "medium",
                    "method": "deterministic_locator_match",
                    "review_status": review_status,
                    "evidence": [f"matched fragment_locator: {target}"],
                    "provenance": {
                        "artefact": "propositions.json",
                        "field": "fragment_locator",
                    },
                }
                if resolve_edge["id"] not in seen_edge_ids:
                    seen_edge_ids.add(resolve_edge["id"])
                    edges.append(resolve_edge)

    edges.sort(key=lambda row: (row["type"], row["from"], row["to"], row["id"]))
    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "edges": edges,
    }


def build_effective_law_statements(
    propositions: list[dict[str, Any]],
    *,
    run_id: str,
    relationships: dict[str, Any] | None = None,
    source_fragments: list[dict[str, Any]] | None = None,
    legal_rule_groups: dict[str, Any] | None = None,
    legal_rule_relationships: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build guidance-facing effective law statement bundles.

    When ``legal_rule_groups`` / ``legal_rule_relationships`` are supplied,
    typed ``exception_to`` / ``triggered_by`` edges contribute required context
    (group targets expand one level to retained members). Typed context takes
    precedence over generic locator context for the same proposition.
    """
    # Keep building/accepting proposition-relationship edges for call-site
    # compatibility; statement composition reads typed legal_rule_relationships
    # when supplied (locator context is resolved independently below).
    if relationships is None:
        build_proposition_relationships(
            propositions,
            run_id=run_id,
            source_fragments=source_fragments,
        )
    locator_index = _build_locator_index(propositions)
    typed_by_prop, composition_diagnostics, typed_decision_facts = _collect_typed_required_contexts(
        propositions,
        legal_rule_groups=legal_rule_groups,
        legal_rule_relationships=legal_rule_relationships,
    )
    decision_facts: list[dict[str, Any]] = list(typed_decision_facts)

    resolve_by_prop_target: dict[
        tuple[str, str],
        tuple[ReviewStatus, ResolutionStatus, list[str], str | None],
    ] = {}
    for prop in propositions:
        prop_id = _prop_id(prop)
        source_id = str(prop.get("source_record_id") or "").strip()
        if not prop_id or not source_id:
            continue
        structural_context = structural_context_for_proposition(
            prop,
            source_fragments=source_fragments,
        )
        for target in _all_reference_targets(prop):
            resolve_by_prop_target[(prop_id, target)] = resolve_locator_in_source_detailed(
                source_record_id=source_id,
                target_locator=target,
                propositions=propositions,
                source_fragments=source_fragments,
                structural_context=structural_context,
                locator_index=locator_index,
            )

    host_support: dict[str, dict[str, Any]] = {}
    statements: list[dict[str, Any]] = []

    for prop in propositions:
        prop_id = _prop_id(prop)
        if not prop_id:
            continue
        source_id = str(prop.get("source_record_id") or "").strip()
        targets = _all_reference_targets(prop)
        external_entries, targets = external_context_entries_for_proposition(
            prop,
            internal_targets=targets,
        )
        typed_entries = list(typed_by_prop.get(prop_id) or [])
        typed_prop_ids = _typed_proposition_ids(typed_entries)

        raw_locator_context: list[dict[str, Any]] = list(external_entries)
        for target in targets:
            review_status, res_status, matched_ids, resolution_basis = resolve_by_prop_target.get(
                (prop_id, target),
                ("unresolved", "unresolved", [], "unresolved"),
            )
            # Stable multi-match ordering regardless of proposition input order.
            ordered_matched_ids = sorted(str(pid) for pid in matched_ids if pid)

            context_entry: dict[str, Any] = {
                "kind": _context_kind_for_target(target, prop),
                "locator": target,
                "resolution_status": res_status,
                "proposition_ids": ordered_matched_ids,
            }
            if resolution_basis:
                context_entry["resolution_basis"] = resolution_basis
            raw_locator_context.append(context_entry)

        locator_context = prune_subsumed_locators(
            _filter_self_reference_context(prop_id, raw_locator_context)
        )
        locator_context = _dedupe_locator_context_against_typed(
            locator_context,
            typed_prop_ids=typed_prop_ids,
            typed_entries=typed_entries,
            receiving_proposition_id=prop_id,
            decision_facts=decision_facts,
        )
        # Typed relationship context precedes generic locator context.
        required_context = [*typed_entries, *locator_context]
        resolution_statuses = [
            entry["resolution_status"] for entry in required_context
        ]
        warnings = _warnings_for_required_context(required_context)

        presentation_role = classify_presentation_role(prop)
        standalone_status = classify_standalone_status(prop, resolution_statuses=resolution_statuses or None)
        if typed_entries and standalone_status == "standalone":
            standalone_status = "context_dependent"
        confidence = classify_confidence(prop, standalone_status=standalone_status)

        is_cross_ref = (
            str(prop.get("legal_effect_type") or "") == "cross_reference"
            or str(prop.get("proposition_tier") or "") == "relationship_reference"
        )
        if is_cross_ref:
            presentation_role = "context_connector"
            if standalone_status == "standalone":
                standalone_status = "relationship_only"

        if (
            presentation_role == "supporting_definition"
            and prop.get("is_compliance_relevant") is not True
        ):
            presentation_role = "supporting_definition"
        elif presentation_role == "guidance_matching_candidate" and is_cross_ref:
            presentation_role = "context_connector"

        if (
            is_cross_ref
            and prop.get("is_compliance_relevant") is False
            and presentation_role == "guidance_matching_candidate"
        ):
            presentation_role = "context_connector"

        statement = {
            "id": _statement_id([prop_id], presentation_role),
            "statement_text": str(prop.get("proposition_text") or "").strip(),
            "presentation_role": presentation_role,
            "standalone_status": standalone_status,
            "source_proposition_ids": [prop_id],
            "supporting_proposition_ids": [],
            "required_context": required_context,
            "connector_context": [],
            "warnings": warnings,
            "confidence": confidence,
            "provenance": {
                "source": "derived_from_propositions",
                "method": "deterministic_export_transform",
            },
        }
        statements.append(statement)

        if is_cross_ref:
            resolved_targets: list[tuple[str, str, ContextKind]] = []
            for target in targets:
                review_status, _res_status, matched_ids, _basis = resolve_by_prop_target.get(
                    (prop_id, target),
                    ("unresolved", "unresolved", [], "unresolved"),
                )
                if review_status != "accepted" or len(matched_ids) != 1:
                    continue
                endpoint_id = matched_ids[0]
                if endpoint_id == prop_id:
                    continue
                kind = _context_kind_for_target(target, prop)
                resolved_targets.append((target, endpoint_id, kind))

            resolved_locators = [target for target, _, _ in resolved_targets]
            pruned_targets = [
                (target, endpoint_id, kind)
                for target, endpoint_id, kind in resolved_targets
                if not _has_more_specific_target(target, resolved_locators)
            ]

            for _target, endpoint_id, _kind in pruned_targets:
                entry = host_support.setdefault(
                    endpoint_id,
                    {"supporting_ids": [], "connector_context": []},
                )
                if prop_id not in entry["supporting_ids"]:
                    entry["supporting_ids"].append(prop_id)

            host_entries = [
                (target, endpoint_id)
                for target, endpoint_id, kind in pruned_targets
                if kind == "host_rule"
            ]
            imported_entries = [
                (target, endpoint_id)
                for target, endpoint_id, kind in pruned_targets
                if kind in {"incorporated_rule", "incorporated_factors"}
            ]
            connector_locator = normalize_cross_reference_locator(
                str(prop.get("fragment_locator") or "")
            )
            for host_target, host_endpoint_id in host_entries:
                for imported_target, imported_endpoint_id in imported_entries:
                    host_support[host_endpoint_id]["connector_context"].append(
                        {
                            "kind": "incorporates_context_from",
                            "locator": imported_target,
                            "proposition_ids": [imported_endpoint_id],
                            "via_proposition_ids": [prop_id],
                        }
                    )
                    host_support[imported_endpoint_id]["connector_context"].append(
                        {
                            "kind": "incorporated_elsewhere_by",
                            "locator": connector_locator or str(prop.get("fragment_locator") or ""),
                            "proposition_ids": [prop_id],
                            "target_locator": host_target,
                            "target_proposition_ids": [host_endpoint_id],
                        }
                    )

    stmt_by_source_prop: dict[str, dict[str, Any]] = {
        stmt["source_proposition_ids"][0]: stmt for stmt in statements if stmt["source_proposition_ids"]
    }
    for host_id, extra in host_support.items():
        host_stmt = stmt_by_source_prop.get(host_id)
        if host_stmt is None:
            continue
        for sid in extra["supporting_ids"]:
            if sid not in host_stmt["supporting_proposition_ids"]:
                host_stmt["supporting_proposition_ids"].append(sid)
        if host_stmt.get("presentation_role") != "context_connector":
            for ctx in extra.get("connector_context") or []:
                if ctx not in host_stmt["connector_context"]:
                    host_stmt["connector_context"].append(ctx)
        if host_stmt["supporting_proposition_ids"] and host_stmt["standalone_status"] == "standalone":
            host_stmt["standalone_status"] = "partially_resolved"

    statements.sort(key=lambda row: row["id"])
    decision_facts.sort(
        key=lambda row: (
            str(row.get("fact_kind") or ""),
            str(row.get("receiving_proposition_id") or ""),
            str(row.get("context_kind") or row.get("typed_context_kind") or ""),
            str(row.get("context_proposition_id") or ""),
            str(row.get("legal_rule_relationship_id") or row.get("typed_relationship_id") or ""),
            str(row.get("generic_locator") or ""),
        )
    )
    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "statements": statements,
        "diagnostics": composition_diagnostics,
        "decision_facts": decision_facts,
    }


def attach_effective_law_artifacts(bundle: dict[str, Any]) -> None:
    """Derive relationship, effective-law, and Proposition Matcher candidate artefacts onto an export bundle.

    Construction order:
    retained propositions → locator relationships → legal rule groups →
    legal rule relationships → effective-law statements → Proposition Matcher candidates.
    """
    propositions = bundle.get("propositions")
    if not isinstance(propositions, list) or not propositions:
        return
    run = bundle.get("run")
    run_id = str(run.get("id") if isinstance(run, dict) else "run-unknown")
    bundle_source_fragments = bundle.get("source_fragments")
    source_fragments_list = (
        bundle_source_fragments if isinstance(bundle_source_fragments, list) else None
    )
    relationships = build_proposition_relationships(
        propositions,
        run_id=run_id,
        source_fragments=source_fragments_list,
    )
    bundle["proposition_relationships"] = relationships

    from law_proposition_extractor_pipeline.legal_rule_groups import attach_legal_rule_groups

    attach_legal_rule_groups(bundle)

    from law_proposition_extractor_pipeline.legal_rule_relationships import attach_legal_rule_relationships

    attach_legal_rule_relationships(bundle)

    legal_rule_groups = bundle.get("legal_rule_groups")
    legal_rule_relationships = bundle.get("legal_rule_relationships")
    statements = build_effective_law_statements(
        propositions,
        run_id=run_id,
        relationships=relationships,
        source_fragments=source_fragments_list,
        legal_rule_groups=legal_rule_groups if isinstance(legal_rule_groups, dict) else None,
        legal_rule_relationships=(
            legal_rule_relationships if isinstance(legal_rule_relationships, dict) else None
        ),
    )
    decision_facts = list(statements.pop("decision_facts", []) or [])
    bundle["effective_law_statements"] = statements
    _merge_effective_law_explanations_into_bundle(bundle, decision_facts)

    from law_proposition_extractor_pipeline.proposition_matcher_law_candidates import build_proposition_matcher_law_candidates

    source_inventory = bundle.get("source_inventory")
    bundle["proposition_matcher_law_candidates"] = build_proposition_matcher_law_candidates(
        effective_law_statements=statements,
        propositions=propositions,
        proposition_relationships=relationships,
        source_inventory=source_inventory if isinstance(source_inventory, dict) else None,
        source_fragments=source_fragments_list,
    )

    from law_proposition_extractor_pipeline.composition_trace import attach_composition_traces

    attach_composition_traces(bundle)


def _merge_effective_law_explanations_into_bundle(
    bundle: dict[str, Any],
    decision_facts: Sequence[dict[str, Any]],
) -> None:
    """Append effective-law explanations captured at composition time (no rebuild)."""
    if not decision_facts:
        return
    from law_proposition_extractor_domain import DecisionExplanation
    from law_proposition_extractor_pipeline.heuristics.effective_law_explanations import (
        bind_effective_law_decision_facts,
        build_effective_law_decision_explanations,
    )
    from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
        build_decision_explanations_artifact,
    )
    from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
        merge_decision_explanation_lists,
    )

    statements_payload = bundle.get("effective_law_statements")
    statement_rows: list[dict[str, Any]] = []
    if isinstance(statements_payload, dict):
        rows = statements_payload.get("statements")
        if isinstance(rows, list):
            statement_rows = [row for row in rows if isinstance(row, dict)]

    bound = bind_effective_law_decision_facts(decision_facts, statements=statement_rows)
    new_explanations = build_effective_law_decision_explanations(bound)
    if not new_explanations:
        return

    run = bundle.get("run")
    run_id = str(run.get("id") if isinstance(run, dict) else "run-unknown")
    existing = bundle.get("decision_explanations")
    existing_rows: list[DecisionExplanation] = []
    if isinstance(existing, dict):
        for row in existing.get("decisions") or []:
            if isinstance(row, dict):
                existing_rows.append(DecisionExplanation.model_validate(row))
            elif isinstance(row, DecisionExplanation):
                existing_rows.append(row)
    elif isinstance(existing, list):
        for row in existing:
            if isinstance(row, dict):
                existing_rows.append(DecisionExplanation.model_validate(row))
            elif isinstance(row, DecisionExplanation):
                existing_rows.append(row)

    merged = merge_decision_explanation_lists(existing_rows, new_explanations)
    bundle["decision_explanations"] = build_decision_explanations_artifact(
        run_id=run_id,
        decisions=merged,
    )


def effective_law_payload_digest(payload: dict[str, Any]) -> str:
    """Stable digest for tests."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
