"""Deterministic typed legal relationships (exception_to / triggered_by)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from law_proposition_extractor_domain import LegalRuleRelationship

from law_proposition_extractor_pipeline.context_locator_resolution import (
    LocatorStructuralContext,
    ParsedLocatorRange,
    ParsedLocatorSingle,
    apply_structural_context_to_reference,
    build_canonical_locator,
    normalize_cross_reference_locator,
    parse_locator_reference,
    parse_locator_structural_context,
    resolve_context_locator,
    structural_context_for_proposition,
)
from law_proposition_extractor_pipeline.legal_rule_groups import (
    group_for_canonical_locator,
    group_for_source_fragment,
)

_SCHEMA_VERSION = "1"
_CONFIDENCE = "high"

# Prefer fully-qualified forms before bare instrument/paragraph tokens so that
# ``Paragraph 1 of Article 49a shall not apply`` captures the whole reference,
# not the trailing ``Article 49a`` alone (live BR1 frontier failure mode).
_PARAGRAPH_OF_INSTRUMENT_TOKEN = (
    r"(?:paragraph|para\.?)\s+"
    r"(?:"
    r"\(\s*\d+[a-z]?\s*\)"  # paragraph (1) of Article 49a
    r"|"
    r"\d+[a-z]?(?:\s*\([^)]+\))?"  # paragraph 1 / paragraph 1(a) of …
    r")"
    r"\s+of\s+"
    r"(?:article|regulation|schedule|rule)\s+\d+[a-z]?"
)
_INSTRUMENT_TOKEN = (
    r"(?:article|regulation|schedule|rule|annex|part)\s+\d+[a-z]?"
    r"(?:\([^)]+\))+"  # Article 49a(2) / Article 49a(2)(a)
    r"|"
    r"(?:article|regulation|schedule|rule|annex|part)\s+\d+[a-z]?"
    r"(?:\s*,?\s*(?:paragraph|para\.?)\s+\d+[a-z]?(?:\s*\([^)]+\))?)?"
)
_BARE_RELATIVE_TOKEN = (
    r"(?:paragraph|para\.?)\s+\d+[a-z]?(?:\s*\([^)]+\))?"
    r"|"
    r"sub-?paragraphs?\s*\([^)]+\)"
    r"|"
    r"points?\s*\([^)]+\)"
)
_REF_TOKEN = (
    rf"(?:{_PARAGRAPH_OF_INSTRUMENT_TOKEN}|{_INSTRUMENT_TOKEN}|{_BARE_RELATIVE_TOKEN})"
)

_EXCEPTION_CUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"(?P<cue>(?P<ref>{_REF_TOKEN})\s+shall\s+not\s+apply)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>(?P<ref>{_REF_TOKEN})\s+does\s+not\s+apply)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>by\s+way\s+of\s+derogation\s+from\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>an?\s+exception\s+to\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>exempt\s+from\s+the\s+requirement(?:s)?\s+in\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
)

# Supported trigger cues (source-grounded + grammatical family). Prefer longer
# ``where the cases referred to in X apply`` forms before bare ``where X applies``.
_TRIGGER_CUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"(?P<cue>where\s+the\s+cases\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN})\s+apply)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>where\s+the\s+case\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN})\s+applies)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>where\s+the\s+circumstances\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN})\s+apply)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>where\s+the\s+circumstances\s+in\s+(?P<ref>{_REF_TOKEN})\s+apply)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>in\s+the\s+cases\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>in\s+the\s+case\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>in\s+cases\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>in\s+the\s+circumstances\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN}))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>where\s+(?P<ref>{_REF_TOKEN})\s+applies)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>when\s+the\s+conditions?\s+in\s+(?P<ref>{_REF_TOKEN})\s+are\s+met)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<cue>if\s+the\s+case\s+described\s+in\s+(?P<ref>{_REF_TOKEN})\s+occurs)",
        re.IGNORECASE,
    ),
)

# Near-miss: "cases/circumstances referred to in <ref>" without a supported cue
# frame. Used only for localizable diagnostics (no relationship claimed).
_TRIGGER_NEAR_MISS_PATTERN = re.compile(
    rf"(?:cases?|circumstances)\s+referred\s+to\s+in\s+(?P<ref>{_REF_TOKEN})",
    re.IGNORECASE,
)

_DIAG_TARGET_AMBIGUOUS = "typed_relationship_target_ambiguous"
_DIAG_TARGET_GROUP_MISSING = "typed_relationship_target_group_missing"
_DIAG_REF_NOT_UNIQUE = "typed_relationship_reference_not_uniquely_associated"
_DIAG_CUE_REF_PARSE_FAILED = "typed_relationship_cue_reference_parse_failed"
_DIAG_CUE_REF_NO_MATCHING_TARGET = "typed_relationship_cue_reference_no_matching_target"
_DIAG_NO_SUPPORTED_TRIGGER_CUE = "typed_relationship_no_supported_trigger_cue"
_DIAG_CUE_FOUND_NO_BOUND_REF = "typed_relationship_cue_found_but_no_bound_reference"


def _stable_hash(parts: tuple[str, ...]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def legal_rule_relationship_id(
    *,
    relationship_type: str,
    source_id: str,
    target_kind: str,
    target_id: str,
    referenced_locator: str,
    inference_basis: str,
) -> str:
    """Deterministic relationship id from stable semantic inputs."""
    digest = _stable_hash(
        (
            str(relationship_type).strip(),
            str(source_id).strip(),
            str(target_kind).strip(),
            str(target_id).strip(),
            str(referenced_locator).strip(),
            str(inference_basis).strip(),
        )
    )
    return f"legalrel:{digest}"


def _as_dict(row: Any) -> dict[str, Any] | None:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "model_dump"):
        dumped = row.model_dump()
        return dumped if isinstance(dumped, dict) else None
    return None


def _strip(value: Any) -> str:
    return str(value or "").strip()


def _is_exception_proposition(prop: dict[str, Any]) -> bool:
    effect = _strip(prop.get("legal_effect_type")).lower()
    if effect == "derogation":
        return True
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, Mapping):
        provision = _strip(meta.get("provision_type")).lower()
        if provision == "exception":
            return True
    return False


def _evidence_text(prop: dict[str, Any]) -> str:
    for key in ("proposition_text", "text", "statement_text"):
        text = _strip(prop.get(key))
        if text:
            return text
    return ""


def _reference_targets(prop: dict[str, Any]) -> list[str]:
    """Stable list of explicit reference strings from structured extraction fields."""
    raw = prop.get("explicit_cross_reference_targets")
    if not isinstance(raw, list):
        raw = prop.get("cross_reference_targets")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _strip(item)
        if not text or text.lower().startswith("prop:"):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _canonical_comparison_key(
    text: str,
    structural_context: LocatorStructuralContext | None = None,
) -> str | None:
    """Map reference text to a comparable canonical locator key.

    Uses existing locator parse/canonicalise helpers so that
    ``Paragraph 1 of Article 49a``, ``Article 49a(1)``, and
    ``article 49a, paragraph 1`` compare equal after qualification.
    """
    raw = _strip(text)
    if not raw:
        return None

    structural = parse_locator_structural_context(raw)
    parsed = parse_locator_reference(raw)

    # Prefer multi-segment / instrument parses (qualified forms) over bare
    # structural singles so ``paragraph 1`` can still inherit enclosing context.
    if structural is not None and structural.segments:
        if len(structural.segments) >= 2 or structural.segments[0].kind not in {
            "paragraph",
            "sub-paragraph",
            "point",
        }:
            return build_canonical_locator(list(structural.segments)).lower() or None

    if parsed is None and structural is not None and structural.segments:
        parsed = ParsedLocatorSingle(display=raw, segments=tuple(structural.segments))
    if parsed is None:
        compact = normalize_cross_reference_locator(raw)
        if compact and re.match(
            r"^(regulation|schedule|article|paragraph|annex|part|rule)\b",
            compact,
            re.IGNORECASE,
        ):
            return compact.lower()
        return None

    if structural_context is not None and structural_context.segments:
        if isinstance(parsed, ParsedLocatorSingle) and len(parsed.segments) == 1:
            kind = parsed.segments[0].kind
            if kind in {"paragraph", "sub-paragraph", "point"}:
                parsed = apply_structural_context_to_reference(structural_context, parsed)
        elif isinstance(parsed, ParsedLocatorRange):
            parsed = apply_structural_context_to_reference(structural_context, parsed)

    if isinstance(parsed, ParsedLocatorSingle) and parsed.segments:
        return build_canonical_locator(list(parsed.segments)).lower() or None
    if isinstance(parsed, ParsedLocatorRange):
        # Ranges are not valid typed-relationship targets.
        return None

    compact = normalize_cross_reference_locator(raw)
    if compact and re.match(
        r"^(regulation|schedule|article|paragraph|annex|part|rule)\b",
        compact,
        re.IGNORECASE,
    ):
        return compact.lower()
    return None


def _is_fully_qualified_reference(text: str) -> bool:
    """True when the reference already names an instrument/container (not bare-relative)."""
    key = _canonical_comparison_key(text, structural_context=None)
    if not key:
        return False
    structural = parse_locator_structural_context(text)
    if structural is not None and len(structural.segments) >= 2:
        return True
    parsed = parse_locator_reference(text)
    if isinstance(parsed, ParsedLocatorSingle) and len(parsed.segments) >= 2:
        return True
    if isinstance(parsed, ParsedLocatorSingle) and parsed.segments:
        return parsed.segments[0].kind in {
            "article",
            "regulation",
            "schedule",
            "rule",
            "annex",
            "part",
        }
    return False


def _refs_match(
    cue_ref: str,
    target: str,
    structural_context: LocatorStructuralContext | None = None,
) -> bool:
    cue_key = _canonical_comparison_key(cue_ref, structural_context)
    target_key = _canonical_comparison_key(target, structural_context)
    if cue_key and target_key and cue_key == target_key:
        return True
    # Fallback: harmless whitespace/case differences on normalize-only forms.
    cue_norm = normalize_cross_reference_locator(cue_ref)
    target_norm = normalize_cross_reference_locator(target)
    if not cue_norm or not target_norm:
        return False
    return re.sub(r"\s+", " ", cue_norm.lower()) == re.sub(r"\s+", " ", target_norm.lower())


def _associate_cue_reference(
    cue_ref: str,
    targets: Sequence[str],
    structural_context: LocatorStructuralContext | None = None,
) -> tuple[str | None, str | None]:
    """Associate a cue-captured reference with a resolution locator.

    Precedence:
      1. Unique explicit cross-reference target with the same canonical locator
      2. Canonicalisation of the cue-captured reference itself
      3. Failure (caller emits diagnostic)

    Returns ``(locator_for_resolution, failure_code_or_none)``.
    """
    cue = _strip(cue_ref)
    if not cue:
        return None, _DIAG_CUE_REF_PARSE_FAILED

    matches = [t for t in targets if _refs_match(cue, t, structural_context)]
    if len(matches) > 1:
        # Distinct surface forms that share one canonical key with the cue are
        # equivalent (e.g. ``paragraph 1`` + ``Article 49a(1)``), not ambiguous.
        match_keys = {
            key
            for key in (_canonical_comparison_key(t, structural_context) for t in matches)
            if key
        }
        cue_key = _canonical_comparison_key(cue, structural_context)
        if len(match_keys) == 1 and cue_key and cue_key in match_keys:
            if _is_fully_qualified_reference(cue):
                return cue, None
            return matches[0], None
        return None, _DIAG_REF_NOT_UNIQUE
    if len(matches) == 1:
        # Prefer the cue text when it is already fully qualified so we do not
        # downgrade ``Paragraph 1 of Article 49a`` to a bare ``paragraph 1``
        # structured target that must re-derive the enclosing article.
        if _is_fully_qualified_reference(cue):
            return cue, None
        return matches[0], None

    cue_key = _canonical_comparison_key(cue, structural_context)
    if cue_key:
        return cue, None

    if targets:
        return None, _DIAG_CUE_REF_NO_MATCHING_TARGET
    return None, _DIAG_CUE_REF_PARSE_FAILED


def _find_cued_references(
    text: str,
    targets: Sequence[str],
    patterns: Sequence[re.Pattern[str]],
    structural_context: LocatorStructuralContext | None = None,
) -> list[tuple[str, str, str | None, str | None]]:
    """Return (cue_text, reference_text, associated_target, failure_code) for each cue hit."""
    hits: list[tuple[str, str, str | None, str | None]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            span = match.span("cue")
            if span in seen_spans:
                continue
            seen_spans.add(span)
            cue_text = match.group("cue").strip()
            ref_text = match.group("ref").strip()
            associated, failure = _associate_cue_reference(
                ref_text, targets, structural_context
            )
            hits.append((cue_text, ref_text, associated, failure))
    return hits


def _props_for_fragments(
    propositions: Sequence[dict[str, Any]],
    *,
    source_record_id: str,
    source_snapshot_id: str,
    fragment_ids: Sequence[str],
) -> list[dict[str, Any]]:
    frag_set = {_strip(fid) for fid in fragment_ids if _strip(fid)}
    if not frag_set:
        return []
    out: list[dict[str, Any]] = []
    for prop in propositions:
        if _strip(prop.get("source_record_id") or prop.get("source_document_id")) != source_record_id:
            continue
        if _strip(prop.get("source_snapshot_id")) != source_snapshot_id:
            continue
        if _strip(prop.get("source_fragment_id")) in frag_set:
            out.append(prop)
    return out


def _select_target(
    *,
    resolution: Any,
    groups_payload: dict[str, Any] | None,
    source_record_id: str,
    source_snapshot_id: str,
    propositions: Sequence[dict[str, Any]],
    source_prop_id: str,
) -> tuple[str, str, str | None, str | None] | None | str:
    """Select (target_kind, target_id, target_fragment_id, canonical_locator).

    Returns:
      - tuple on success
      - diagnostic code string when strong evidence cannot safely emit
      - None when no target and no diagnostic
    """
    resolved_locator = _strip(getattr(resolution, "resolved_locator", None))
    matched_fragment_ids = [
        _strip(fid) for fid in (getattr(resolution, "matched_fragment_ids", None) or []) if _strip(fid)
    ]
    prop_ids = [
        _strip(pid) for pid in (getattr(resolution, "proposition_ids", None) or []) if _strip(pid)
    ]

    if resolved_locator:
        group = group_for_canonical_locator(
            groups_payload,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
            canonical_locator=resolved_locator,
        )
        if group is not None:
            return (
                "legal_rule_group",
                _strip(group.get("id")),
                _strip(group.get("source_fragment_id")) or None,
                _strip(group.get("canonical_locator")) or resolved_locator,
            )

    fragment_groups: list[dict[str, Any]] = []
    for frag_id in matched_fragment_ids:
        group = group_for_source_fragment(
            groups_payload,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
            source_fragment_id=frag_id,
        )
        if group is not None:
            fragment_groups.append(group)
    unique_by_id = {_strip(g.get("id")): g for g in fragment_groups if _strip(g.get("id"))}
    if len(unique_by_id) == 1:
        group = next(iter(unique_by_id.values()))
        return (
            "legal_rule_group",
            _strip(group.get("id")),
            _strip(group.get("source_fragment_id")) or None,
            _strip(group.get("canonical_locator")) or resolved_locator or None,
        )
    if len(unique_by_id) > 1:
        return _DIAG_TARGET_AMBIGUOUS

    # No group: unique proposition on resolved fragment(s) only.
    if len(matched_fragment_ids) == 1:
        members = _props_for_fragments(
            propositions,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
            fragment_ids=matched_fragment_ids,
        )
        if len(members) == 1:
            member = members[0]
            member_locator = _strip(member.get("fragment_locator")).split(" (", 1)[0].strip()
            return (
                "proposition",
                _strip(member.get("id")),
                matched_fragment_ids[0],
                member_locator or resolved_locator or None,
            )
        if len(members) > 1:
            return _DIAG_TARGET_GROUP_MISSING

    retained_prop_ids = [
        pid
        for pid in prop_ids
        if any(_strip(p.get("id")) == pid for p in propositions)
        and pid != source_prop_id
    ]
    # Fall back to resolution proposition_ids when fragment membership is empty.
    if not matched_fragment_ids and len(retained_prop_ids) == 1:
        target_id = retained_prop_ids[0]
        target_prop = next((p for p in propositions if _strip(p.get("id")) == target_id), None)
        return (
            "proposition",
            target_id,
            _strip(target_prop.get("source_fragment_id")) if target_prop else None,
            resolved_locator
            or (_strip(target_prop.get("fragment_locator")) if target_prop else None)
            or None,
        )
    if len(retained_prop_ids) > 1:
        return _DIAG_TARGET_AMBIGUOUS
    if len(matched_fragment_ids) > 1 and not unique_by_id:
        return _DIAG_TARGET_AMBIGUOUS

    # Strong cue + unique resolution status but nowhere to land.
    if getattr(resolution, "resolved", False) and (resolved_locator or matched_fragment_ids):
        return _DIAG_TARGET_GROUP_MISSING
    return None


def _diagnostic(
    code: str,
    *,
    source_id: str,
    relationship_type: str,
    referenced_locator: str | None = None,
    detail: str | None = None,
    cue_text: str | None = None,
    reference_text: str | None = None,
    canonical_cue_locator: str | None = None,
    available_resolved_targets: Sequence[str] | None = None,
    source_fragment_id: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": code,
        "source_id": source_id,
        "relationship_type": relationship_type,
    }
    if referenced_locator:
        row["referenced_locator"] = referenced_locator
    if detail:
        row["detail"] = detail
    if cue_text:
        row["cue_text"] = cue_text
    if reference_text:
        row["reference_text"] = reference_text
    if canonical_cue_locator:
        row["canonical_cue_locator"] = canonical_cue_locator
    if available_resolved_targets is not None:
        row["available_resolved_targets"] = list(available_resolved_targets)
    if source_fragment_id:
        row["source_fragment_id"] = source_fragment_id
    return row


def _emit_relationship(
    *,
    relationship_type: str,
    inference_basis: str,
    source_prop: dict[str, Any],
    cue_text: str,
    reference_text: str,
    referenced_locator: str,
    resolution_basis: str | None,
    target_kind: str,
    target_id: str,
    target_fragment_id: str | None,
    target_canonical_locator: str | None,
    evidence_text: str,
) -> LegalRuleRelationship:
    source_id = _strip(source_prop.get("id"))
    return LegalRuleRelationship(
        id=legal_rule_relationship_id(
            relationship_type=relationship_type,
            source_id=source_id,
            target_kind=target_kind,
            target_id=target_id,
            referenced_locator=referenced_locator,
            inference_basis=inference_basis,
        ),
        relationship_type=relationship_type,  # type: ignore[arg-type]
        source_kind="proposition",
        source_id=source_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=target_id,
        source_record_id=_strip(source_prop.get("source_record_id") or source_prop.get("source_document_id")),
        source_snapshot_id=_strip(source_prop.get("source_snapshot_id")),
        source_fragment_id=_strip(source_prop.get("source_fragment_id")) or None,
        target_source_fragment_id=target_fragment_id,
        referenced_locator=referenced_locator,
        reference_text=reference_text,
        resolution_basis=resolution_basis,  # type: ignore[arg-type]
        inference_basis=inference_basis,  # type: ignore[arg-type]
        evidence_text=evidence_text or None,
        cue_text=cue_text or None,
        confidence=_CONFIDENCE,
        target_canonical_locator=target_canonical_locator,
    )


def _try_build_for_cue(
    *,
    relationship_type: str,
    inference_basis: str,
    source_prop: dict[str, Any],
    cue_text: str,
    reference_text: str,
    associated_target: str | None,
    association_failure: str | None,
    available_targets: Sequence[str],
    structural_context: LocatorStructuralContext | None,
    propositions: Sequence[dict[str, Any]],
    source_fragments: Sequence[dict[str, Any]] | None,
    groups_payload: dict[str, Any] | None,
    diagnostics: list[dict[str, Any]],
    decision_facts: list[dict[str, Any]] | None = None,
) -> LegalRuleRelationship | None:
    source_id = _strip(source_prop.get("id"))
    source_record_id = _strip(source_prop.get("source_record_id") or source_prop.get("source_document_id"))
    source_snapshot_id = _strip(source_prop.get("source_snapshot_id"))
    source_fragment_id = _strip(source_prop.get("source_fragment_id")) or None
    if not source_id or not source_record_id or not source_snapshot_id:
        return None

    cue_canon = _canonical_comparison_key(reference_text, structural_context)
    facts = decision_facts if decision_facts is not None else None

    def _candidate_id(diagnostic_code: str = "") -> str:
        from law_proposition_extractor_pipeline.heuristics.relationship_explanations import (
            relationship_candidate_id,
        )

        return relationship_candidate_id(
            source_proposition_id=source_id,
            relationship_type=relationship_type,
            cue_text=cue_text,
            reference_text=reference_text,
            canonical_locator=cue_canon or "",
            diagnostic_code=diagnostic_code,
        )

    def _unselected_ordinary() -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for target in available_targets:
            if _refs_match(reference_text, target, structural_context):
                continue
            if associated_target and _refs_match(
                associated_target, target, structural_context
            ):
                continue
            out.append(
                {
                    "reference_text": target,
                    "reason": "outside_typed_relationship_cue",
                }
            )
        return out

    def _record_unresolved(code: str, *, detail: str | None = None) -> None:
        if facts is None:
            return
        facts.append(
            {
                "fact_kind": "inference_unresolved",
                "candidate_id": _candidate_id(code),
                "source_proposition_id": source_id,
                "source_fragment_id": source_fragment_id,
                "relationship_type": relationship_type,
                "cue_text": cue_text,
                "reference_text": reference_text,
                "canonical_target_locator": cue_canon,
                "diagnostic_code": code,
                "detail": detail,
                "available_resolved_targets": list(available_targets),
                "relationship_claimed": False,
            }
        )

    if associated_target is None:
        # Prefer specific association codes; fall back to cue-found-but-unbound.
        code = association_failure or _DIAG_CUE_FOUND_NO_BOUND_REF
        detail = {
            _DIAG_REF_NOT_UNIQUE: "exception/trigger cue could not be uniquely associated with one reference",
            _DIAG_CUE_REF_PARSE_FAILED: "cue-captured reference could not be parsed to a canonical locator",
            _DIAG_CUE_REF_NO_MATCHING_TARGET: (
                "cue-captured reference did not match any explicit cross-reference target "
                "and could not be canonicalised"
            ),
            _DIAG_CUE_FOUND_NO_BOUND_REF: (
                "supported trigger/exception cue found but no cue-bound reference could be selected"
            ),
        }.get(code, "typed relationship cue association failed")
        diagnostics.append(
            _diagnostic(
                code,
                source_id=source_id,
                relationship_type=relationship_type,
                referenced_locator=(
                    cue_canon
                    or normalize_cross_reference_locator(reference_text)
                    or reference_text
                ),
                detail=detail,
                cue_text=cue_text,
                reference_text=reference_text,
                canonical_cue_locator=cue_canon,
                available_resolved_targets=available_targets,
                source_fragment_id=source_fragment_id,
            )
        )
        _record_unresolved(code, detail=detail)
        return None

    locator_for_resolution = associated_target
    resolution = resolve_context_locator(
        locator_for_resolution,
        source_record_id=source_record_id,
        source_fragments=list(source_fragments or []),
        structural_context=structural_context
        or structural_context_for_proposition(
            source_prop,
            source_fragments=source_fragments,
        ),
        propositions=list(propositions),
    )

    if not resolution.resolved or resolution.review_status != "accepted":
        # Strong cue but unresolved/ambiguous reference — diagnose only when ambiguous
        # (intended target exists but is not unique) or unresolved with fragments present.
        if resolution.review_status == "ambiguous":
            diagnostics.append(
                _diagnostic(
                    _DIAG_TARGET_AMBIGUOUS,
                    source_id=source_id,
                    relationship_type=relationship_type,
                    referenced_locator=_strip(resolution.resolved_locator)
                    or cue_canon
                    or associated_target,
                    detail="cued reference resolved ambiguously",
                    cue_text=cue_text,
                    reference_text=reference_text,
                    canonical_cue_locator=cue_canon,
                    available_resolved_targets=available_targets,
                    source_fragment_id=source_fragment_id,
                )
            )
            _record_unresolved(
                _DIAG_TARGET_AMBIGUOUS,
                detail="cued reference resolved ambiguously",
            )
        return None

    basis = _strip(resolution.resolution_basis)
    if basis not in {"explicit", "structural_relative", "instrument_wide"}:
        basis = "explicit"

    referenced_locator = (
        _strip(resolution.resolved_locator)
        or cue_canon
        or normalize_cross_reference_locator(associated_target)
        or associated_target
    )

    selected = _select_target(
        resolution=resolution,
        groups_payload=groups_payload,
        source_record_id=source_record_id,
        source_snapshot_id=source_snapshot_id,
        propositions=propositions,
        source_prop_id=source_id,
    )
    if selected is None:
        return None
    if isinstance(selected, str):
        diagnostics.append(
            _diagnostic(
                selected,
                source_id=source_id,
                relationship_type=relationship_type,
                referenced_locator=referenced_locator,
                cue_text=cue_text,
                reference_text=reference_text,
                canonical_cue_locator=cue_canon,
                available_resolved_targets=available_targets,
                source_fragment_id=source_fragment_id,
            )
        )
        _record_unresolved(selected)
        return None

    target_kind, target_id, target_frag, target_canon = selected
    if not target_id:
        return None

    # Prefer structural/group canonical locator over display forms like "article 49a(1)".
    referenced_locator = (
        target_canon
        or referenced_locator
        or cue_canon
        or normalize_cross_reference_locator(associated_target)
        or associated_target
    )

    rel = _emit_relationship(
        relationship_type=relationship_type,
        inference_basis=inference_basis,
        source_prop=source_prop,
        cue_text=cue_text,
        reference_text=reference_text,
        referenced_locator=referenced_locator,
        resolution_basis=basis,
        target_kind=target_kind,
        target_id=target_id,
        target_fragment_id=target_frag,
        target_canonical_locator=target_canon or referenced_locator,
        evidence_text=_evidence_text(source_prop),
    )

    if facts is not None:
        infer_kind = (
            "infer_exception_to"
            if relationship_type == "exception_to"
            else "infer_triggered_by"
        )
        facts.append(
            {
                "fact_kind": infer_kind,
                "relationship_id": rel.id,
                "source_proposition_id": source_id,
                "source_fragment_id": source_fragment_id,
                "relationship_type": relationship_type,
                "cue_text": cue_text,
                "cue_basis": inference_basis,
                "inference_basis": inference_basis,
                "reference_text": reference_text,
                "matched_resolved_reference": associated_target,
                "canonical_target_locator": referenced_locator,
                "resolution_basis": basis,
                "confidence": _CONFIDENCE,
                "available_resolved_targets": list(available_targets),
                "unselected_ordinary_references": _unselected_ordinary(),
            }
        )
        member_ids: list[str] = []
        selection_basis = "unique_proposition"
        if target_kind == "legal_rule_group" and isinstance(groups_payload, Mapping):
            selection_basis = "unique_legal_rule_group"
            for group in groups_payload.get("groups") or []:
                if not isinstance(group, Mapping):
                    continue
                if _strip(group.get("id")) != target_id:
                    continue
                member_ids = [
                    _strip(m)
                    for m in (group.get("member_proposition_ids") or [])
                    if _strip(m)
                ]
                break
        facts.append(
            {
                "fact_kind": "prefer_group_target",
                "relationship_id": rel.id,
                "target_kind": target_kind,
                "target_id": target_id,
                "target_fragment_id": target_frag,
                "canonical_target_locator": referenced_locator,
                "source_record_id": source_record_id,
                "source_snapshot_id": source_snapshot_id,
                "member_proposition_ids": member_ids,
                "selection_basis": selection_basis,
            }
        )

    return rel


def build_legal_rule_relationships(
    propositions: Sequence[Any],
    *,
    run_id: str,
    source_fragments: Sequence[Any] | None = None,
    legal_rule_groups: dict[str, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build typed legal relationships from explicit exception/trigger cues.

    Requires retained/exported propositions, resolved context locators, and
    legal rule groups. Only emits edges with high-confidence cue→reference
    association; does not expand group membership onto member propositions
    at persistence time (effective-law composition expands one level later).
    """
    props: list[dict[str, Any]] = []
    for row in propositions:
        prop = _as_dict(row)
        if prop is None:
            continue
        if not _strip(prop.get("id")):
            continue
        props.append(prop)

    fragments: list[dict[str, Any]] = []
    for row in source_fragments or []:
        frag = _as_dict(row)
        if frag is not None:
            fragments.append(frag)

    groups_payload: dict[str, Any] | None
    if isinstance(legal_rule_groups, Mapping):
        groups_payload = dict(legal_rule_groups)
    elif isinstance(legal_rule_groups, Sequence):
        groups_payload = {"groups": [g for g in legal_rule_groups if isinstance(g, dict)]}
    else:
        groups_payload = None

    relationships: list[LegalRuleRelationship] = []
    diagnostics: list[dict[str, Any]] = []
    decision_facts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for prop in props:
        text = _evidence_text(prop)
        if not text:
            continue
        targets = _reference_targets(prop)
        structural_context = structural_context_for_proposition(
            prop,
            source_fragments=fragments,
        )

        if _is_exception_proposition(prop):
            for cue_text, ref_text, associated, failure in _find_cued_references(
                text, targets, _EXCEPTION_CUE_PATTERNS, structural_context
            ):
                rel = _try_build_for_cue(
                    relationship_type="exception_to",
                    inference_basis="explicit_exception_cue",
                    source_prop=prop,
                    cue_text=cue_text,
                    reference_text=ref_text,
                    associated_target=associated,
                    association_failure=failure,
                    available_targets=targets,
                    structural_context=structural_context,
                    propositions=props,
                    source_fragments=fragments,
                    groups_payload=groups_payload,
                    diagnostics=diagnostics,
                    decision_facts=decision_facts,
                )
                if rel is not None and rel.id not in seen_ids:
                    seen_ids.add(rel.id)
                    relationships.append(rel)

        trigger_hits = _find_cued_references(
            text, targets, _TRIGGER_CUE_PATTERNS, structural_context
        )
        for cue_text, ref_text, associated, failure in trigger_hits:
            rel = _try_build_for_cue(
                relationship_type="triggered_by",
                inference_basis="explicit_trigger_cue",
                source_prop=prop,
                cue_text=cue_text,
                reference_text=ref_text,
                associated_target=associated,
                association_failure=failure,
                available_targets=targets,
                structural_context=structural_context,
                propositions=props,
                source_fragments=fragments,
                groups_payload=groups_payload,
                diagnostics=diagnostics,
                decision_facts=decision_facts,
            )
            if rel is not None and rel.id not in seen_ids:
                seen_ids.add(rel.id)
                relationships.append(rel)

        # Localize near-miss trigger language without claiming a relationship.
        # Silent for propositions with no plausible "referred to in" trigger frame.
        if not trigger_hits:
            near = _TRIGGER_NEAR_MISS_PATTERN.search(text)
            if near is not None:
                source_id = _strip(prop.get("id"))
                ref_text = near.group("ref").strip()
                cue_span = near.group(0).strip()
                diagnostics.append(
                    _diagnostic(
                        _DIAG_NO_SUPPORTED_TRIGGER_CUE,
                        source_id=source_id,
                        relationship_type="triggered_by",
                        referenced_locator=(
                            _canonical_comparison_key(ref_text, structural_context)
                            or normalize_cross_reference_locator(ref_text)
                            or ref_text
                        ),
                        detail=(
                            "proposition contains 'referred to in' trigger-like language "
                            "but no supported trigger cue frame matched"
                        ),
                        cue_text=cue_span,
                        reference_text=ref_text,
                        canonical_cue_locator=_canonical_comparison_key(
                            ref_text, structural_context
                        ),
                        available_resolved_targets=targets,
                        source_fragment_id=_strip(prop.get("source_fragment_id")) or None,
                    )
                )
                decision_facts.append(
                    {
                        "fact_kind": "inference_unresolved",
                        "candidate_id": f"trigger-near-miss:{source_id}",
                        "source_proposition_id": source_id,
                        "source_fragment_id": _strip(prop.get("source_fragment_id")) or None,
                        "relationship_type": "triggered_by",
                        "cue_text": cue_span,
                        "reference_text": ref_text,
                        "canonical_target_locator": _canonical_comparison_key(
                            ref_text, structural_context
                        ),
                        "diagnostic_code": _DIAG_NO_SUPPORTED_TRIGGER_CUE,
                        "detail": (
                            "proposition contains 'referred to in' trigger-like language "
                            "but no supported trigger cue frame matched"
                        ),
                        "available_resolved_targets": list(targets),
                        "relationship_claimed": False,
                    }
                )

    relationships.sort(
        key=lambda r: (
            r.relationship_type,
            r.source_id,
            r.target_kind,
            r.target_id,
            r.id,
        )
    )
    # Deterministic diagnostic ordering; dedupe identical diagnostic rows.
    diag_keys: set[tuple[str, ...]] = set()
    ordered_diags: list[dict[str, Any]] = []
    for row in sorted(
        diagnostics,
        key=lambda d: (
            _strip(d.get("code")),
            _strip(d.get("source_id")),
            _strip(d.get("relationship_type")),
            _strip(d.get("referenced_locator")),
            _strip(d.get("detail")),
        ),
    ):
        key = (
            _strip(row.get("code")),
            _strip(row.get("source_id")),
            _strip(row.get("relationship_type")),
            _strip(row.get("referenced_locator")),
            _strip(row.get("detail")),
        )
        if key in diag_keys:
            continue
        diag_keys.add(key)
        ordered_diags.append(row)

    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "relationships": [r.model_dump() for r in relationships],
        "diagnostics": ordered_diags,
        "decision_facts": decision_facts,
    }


def _merge_relationship_explanations_into_bundle(
    bundle: dict[str, Any],
    decision_facts: Sequence[dict[str, Any]],
) -> None:
    """Append relationship explanations captured at inference time (no rebuild)."""
    if not decision_facts:
        return
    from law_proposition_extractor_domain import DecisionExplanation

    from law_proposition_extractor_pipeline.heuristics.relationship_explanations import (
        build_relationship_decision_explanations,
    )
    from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
        build_decision_explanations_artifact,
    )
    from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
        merge_decision_explanation_lists,
    )

    new_explanations = build_relationship_decision_explanations(decision_facts)
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


def attach_legal_rule_relationships(bundle: dict[str, Any]) -> None:
    """Derive ``legal_rule_relationships`` onto an export bundle."""
    propositions = bundle.get("propositions")
    if not isinstance(propositions, list):
        propositions = []
    run = bundle.get("run")
    run_id = str(run.get("id") if isinstance(run, dict) else "run-unknown")
    source_fragments = bundle.get("source_fragments")
    groups = bundle.get("legal_rule_groups")
    payload = build_legal_rule_relationships(
        propositions,
        run_id=run_id,
        source_fragments=source_fragments if isinstance(source_fragments, list) else None,
        legal_rule_groups=groups if isinstance(groups, (dict, list)) else None,
    )
    decision_facts = list(payload.pop("decision_facts", []) or [])
    bundle["legal_rule_relationships"] = payload
    _merge_relationship_explanations_into_bundle(bundle, decision_facts)
