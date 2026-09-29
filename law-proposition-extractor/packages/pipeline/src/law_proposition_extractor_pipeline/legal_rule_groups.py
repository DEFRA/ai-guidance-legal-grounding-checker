"""Deterministic legal rule groups for multi-proposition source fragments."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import LegalRuleGroup

_SCHEMA_VERSION = "1"
_GROUP_BASIS = "shared_source_fragment"
_UNRELIABLE_LOCATORS = frozenset({"", "unknown", "document:full", "n/a", "none"})


def _stable_hash(parts: tuple[str, ...]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def legal_rule_group_id(
    *,
    source_snapshot_id: str,
    source_fragment_id: str,
    canonical_locator: str,
    group_basis: str = _GROUP_BASIS,
) -> str:
    """Deterministic group id from stable source identity (not member order)."""
    digest = _stable_hash(
        (
            str(source_snapshot_id).strip(),
            str(source_fragment_id).strip(),
            str(canonical_locator).strip(),
            str(group_basis).strip(),
        )
    )
    return f"rulegrp:{digest}"


def _as_dict(row: Any) -> dict[str, Any] | None:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "model_dump"):
        dumped = row.model_dump()
        return dumped if isinstance(dumped, dict) else None
    return None


def _strip(value: Any) -> str:
    return str(value or "").strip()


def _is_reliable_locator(locator: str) -> bool:
    normalized = locator.strip().lower()
    return bool(normalized) and normalized not in _UNRELIABLE_LOCATORS


def _fragment_index(
    source_fragments: Sequence[Any] | None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in source_fragments or []:
        frag = _as_dict(row)
        if frag is None:
            continue
        frag_id = _strip(frag.get("id") or frag.get("fragment_id"))
        if frag_id:
            index[frag_id] = frag
    return index


def _member_sort_key(prop: dict[str, Any]) -> tuple[Any, ...]:
    """Source order when available; deterministic fallback otherwise."""
    for key in ("source_order", "order_index", "extraction_order"):
        raw = prop.get(key)
        if raw is None:
            continue
        try:
            return (0, int(raw), _strip(prop.get("id")))
        except (TypeError, ValueError):
            continue
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, Mapping):
        for key in ("source_order", "order_index", "extraction_order"):
            raw = meta.get(key)
            if raw is None:
                continue
            try:
                return (0, int(raw), _strip(prop.get("id")))
            except (TypeError, ValueError):
                continue
    return (1, _strip(prop.get("fragment_locator")).lower(), _strip(prop.get("id")))


def _canonical_locator_for_bucket(
    members: Sequence[dict[str, Any]],
    *,
    fragment: dict[str, Any] | None,
) -> str | None:
    if fragment is not None:
        locator = _strip(fragment.get("locator"))
        if _is_reliable_locator(locator):
            return locator
    locators = sorted(
        {
            _strip(prop.get("fragment_locator"))
            for prop in members
            if _is_reliable_locator(_strip(prop.get("fragment_locator")))
        }
    )
    if len(locators) == 1:
        return locators[0]
    # Prefer the shortest shared structural stem when members carry annotated locators
    # (e.g. "article:49a:paragraph:1 (first sentence)").
    stems = sorted(
        {
            loc.split(" (", 1)[0].strip()
            for loc in (
                _strip(prop.get("fragment_locator")) for prop in members
            )
            if _is_reliable_locator(loc.split(" (", 1)[0].strip())
        }
    )
    if len(stems) == 1:
        return stems[0]
    return None


def build_legal_rule_groups(
    propositions: Sequence[Any],
    *,
    run_id: str,
    source_fragments: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build legal rule groups from retained/exported propositions.

    Construction rule: create one group when two or more retained propositions
    share the same ``source_record_id``, ``source_snapshot_id``, and
    ``source_fragment_id``, and that fragment has a reliable canonical locator.
    Membership is direct-fragment only (no descendants, no article aggregates,
    no soft-duplicate clustering).
    """
    fragments = _fragment_index(source_fragments)
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in propositions:
        prop = _as_dict(row)
        if prop is None:
            continue
        prop_id = _strip(prop.get("id"))
        source_record_id = _strip(prop.get("source_record_id") or prop.get("source_document_id"))
        source_snapshot_id = _strip(prop.get("source_snapshot_id"))
        source_fragment_id = _strip(prop.get("source_fragment_id"))
        if not prop_id or not source_record_id or not source_snapshot_id or not source_fragment_id:
            continue
        buckets[(source_record_id, source_snapshot_id, source_fragment_id)].append(prop)

    groups: list[LegalRuleGroup] = []
    decision_facts: list[dict[str, Any]] = []
    for (source_record_id, source_snapshot_id, source_fragment_id), members in buckets.items():
        if len(members) < 2:
            continue
        # Guard: never mix snapshots/records inside a bucket key (by construction).
        if any(
            _strip(m.get("source_record_id") or m.get("source_document_id")) != source_record_id
            or _strip(m.get("source_snapshot_id")) != source_snapshot_id
            or _strip(m.get("source_fragment_id")) != source_fragment_id
            for m in members
        ):
            continue
        fragment = fragments.get(source_fragment_id)
        if fragment is not None:
            frag_record = _strip(fragment.get("source_record_id"))
            frag_snapshot = _strip(fragment.get("source_snapshot_id"))
            if frag_record and frag_record != source_record_id:
                continue
            if frag_snapshot and frag_snapshot != source_snapshot_id:
                continue
        canonical_locator = _canonical_locator_for_bucket(members, fragment=fragment)
        if canonical_locator is None:
            continue
        ordered_members = sorted(members, key=_member_sort_key)
        member_ids = [_strip(m.get("id")) for m in ordered_members]
        group = LegalRuleGroup(
            id=legal_rule_group_id(
                source_snapshot_id=source_snapshot_id,
                source_fragment_id=source_fragment_id,
                canonical_locator=canonical_locator,
                group_basis=_GROUP_BASIS,
            ),
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
            source_fragment_id=source_fragment_id,
            canonical_locator=canonical_locator,
            member_proposition_ids=member_ids,
            group_basis=_GROUP_BASIS,
            member_count=len(member_ids),
            fragment_kind=_strip(fragment.get("fragment_type")) or None if fragment else None,
            parent_fragment_id=(
                _strip(fragment.get("parent_fragment_id")) or None if fragment else None
            ),
        )
        groups.append(group)
        decision_facts.append(
            {
                "fact_kind": "create_shared_fragment_rule_group",
                "group_id": group.id,
                "source_record_id": source_record_id,
                "source_snapshot_id": source_snapshot_id,
                "source_fragment_id": source_fragment_id,
                "canonical_locator": canonical_locator,
                "group_basis": _GROUP_BASIS,
                "member_proposition_ids": list(member_ids),
                "member_count": len(member_ids),
                "minimum_member_count": 2,
            }
        )

    groups.sort(
        key=lambda g: (
            g.source_record_id,
            g.source_snapshot_id,
            g.canonical_locator,
            g.source_fragment_id,
            g.id,
        )
    )
    decision_facts.sort(
        key=lambda row: (
            str(row.get("source_record_id") or ""),
            str(row.get("source_snapshot_id") or ""),
            str(row.get("canonical_locator") or ""),
            str(row.get("source_fragment_id") or ""),
            str(row.get("group_id") or ""),
        )
    )
    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_id,
        "groups": [g.model_dump() for g in groups],
        "decision_facts": decision_facts,
    }


def _groups_list(payload: dict[str, Any] | Sequence[Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, Mapping):
        rows = payload.get("groups")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return []
    return [row for row in payload if isinstance(row, dict)]


def groups_by_source_fragment_id(
    payload: dict[str, Any] | Sequence[Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Index groups by ``source_fragment_id`` (may span instruments; prefer scoped helpers)."""
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in _groups_list(payload):
        frag_id = _strip(group.get("source_fragment_id"))
        if frag_id:
            indexed[frag_id].append(group)
    return dict(indexed)


def group_for_source_fragment(
    payload: dict[str, Any] | Sequence[Any] | None,
    *,
    source_record_id: str,
    source_snapshot_id: str,
    source_fragment_id: str,
) -> dict[str, Any] | None:
    """Return the unique group for a source-scoped fragment, if present."""
    record_id = _strip(source_record_id)
    snapshot_id = _strip(source_snapshot_id)
    fragment_id = _strip(source_fragment_id)
    matches = [
        group
        for group in _groups_list(payload)
        if _strip(group.get("source_record_id")) == record_id
        and _strip(group.get("source_snapshot_id")) == snapshot_id
        and _strip(group.get("source_fragment_id")) == fragment_id
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def group_for_canonical_locator(
    payload: dict[str, Any] | Sequence[Any] | None,
    *,
    source_record_id: str,
    source_snapshot_id: str,
    canonical_locator: str,
) -> dict[str, Any] | None:
    """Return the unique group for a source/snapshot-scoped canonical locator."""
    record_id = _strip(source_record_id)
    snapshot_id = _strip(source_snapshot_id)
    locator = _strip(canonical_locator)
    matches = [
        group
        for group in _groups_list(payload)
        if _strip(group.get("source_record_id")) == record_id
        and _strip(group.get("source_snapshot_id")) == snapshot_id
        and _strip(group.get("canonical_locator")) == locator
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _merge_grouping_explanations_into_bundle(
    bundle: dict[str, Any],
    decision_facts: Sequence[dict[str, Any]],
) -> None:
    """Append grouping explanations captured at construction time (no rebuild)."""
    if not decision_facts:
        return
    from law_proposition_extractor_domain import DecisionExplanation
    from law_proposition_extractor_pipeline.heuristics.grouping_explanations import (
        build_grouping_decision_explanations,
    )
    from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
        build_decision_explanations_artifact,
    )
    from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
        merge_decision_explanation_lists,
    )

    new_explanations = build_grouping_decision_explanations(decision_facts)
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


def attach_legal_rule_groups(bundle: dict[str, Any]) -> None:
    """Derive ``legal_rule_groups`` onto an export bundle from retained propositions."""
    propositions = bundle.get("propositions")
    if not isinstance(propositions, list):
        propositions = []
    run = bundle.get("run")
    run_id = str(run.get("id") if isinstance(run, dict) else "run-unknown")
    source_fragments = bundle.get("source_fragments")
    payload = build_legal_rule_groups(
        propositions,
        run_id=run_id,
        source_fragments=source_fragments if isinstance(source_fragments, list) else None,
    )
    decision_facts = list(payload.pop("decision_facts", []) or [])
    bundle["legal_rule_groups"] = payload
    _merge_grouping_explanations_into_bundle(bundle, decision_facts)
