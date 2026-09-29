"""Structural parent validation for source fragments."""

from __future__ import annotations

from typing import Any

_TOP_LEVEL_PROVISION_KINDS = frozenset(
    {
        "article",
        "regulation",
        "rule",
        "section",
        "annex",
        "schedule",
    }
)
_CONTAINER_KINDS = frozenset(
    {
        "part",
        "chapter",
        "title",
        "division",
        "document",
        "instrument",
    }
)


def _strip(value: Any) -> str:
    return str(value or "").strip()


def locator_kind(locator: str) -> str:
    head = _strip(locator).split(":", maxsplit=1)[0].lower()
    return head


def is_top_level_provision_locator(locator: str) -> bool:
    parts = [part for part in _strip(locator).lower().split(":") if part]
    if len(parts) != 2:
        return False
    return parts[0] in _TOP_LEVEL_PROVISION_KINDS


def is_container_locator(locator: str) -> bool:
    kind = locator_kind(locator)
    if kind in _CONTAINER_KINDS:
        return True
    # document:full and similar placeholders
    return _strip(locator).lower() in {"document:full", "document:root"}


def is_locator_structural_ancestor(candidate: str, descendant: str) -> bool:
    """True when candidate locator is a proper structural ancestor of descendant.

    Prefer explicit locator path prefixes. Container→provision edges that are not
    path-prefixes are validated separately via kind rules.
    """
    parent = _strip(candidate).lower()
    child = _strip(descendant).lower()
    if not parent or not child or parent == child:
        return False
    if child.startswith(f"{parent}:"):
        return True
    return False


def is_valid_structural_parent(
    *,
    parent_locator: str | None,
    child_locator: str | None,
    parent_source_record_id: str | None = None,
    child_source_record_id: str | None = None,
    parent_snapshot_id: str | None = None,
    child_snapshot_id: str | None = None,
    parent_id: str | None = None,
    child_id: str | None = None,
) -> bool:
    """Return whether a parent→child edge is a plausible structural ancestry link."""
    parent_loc = _strip(parent_locator)
    child_loc = _strip(child_locator)
    if not parent_loc or not child_loc:
        return False
    if parent_id and child_id and _strip(parent_id) == _strip(child_id):
        return False
    if parent_source_record_id and child_source_record_id:
        if _strip(parent_source_record_id) != _strip(child_source_record_id):
            return False
    if parent_snapshot_id and child_snapshot_id:
        if _strip(parent_snapshot_id) != _strip(child_snapshot_id):
            return False
    if is_locator_structural_ancestor(parent_loc, child_loc):
        return True
    # Genuine container parenting a top-level provision (part → article).
    if is_container_locator(parent_loc) and is_top_level_provision_locator(child_loc):
        return True
    # Container nesting (part → chapter, chapter → title, etc.).
    if is_container_locator(parent_loc) and is_container_locator(child_loc):
        return True
    # Sibling top-level provisions are never valid parent/child.
    if is_top_level_provision_locator(parent_loc) and is_top_level_provision_locator(child_loc):
        return False
    return False


def validate_source_fragment_hierarchy(
    fragments: list[dict[str, Any]] | list[Any],
) -> list[dict[str, Any]]:
    """Return non-blocking hierarchy diagnostics for fragment parent links.

    Designed for lint/load paths: malformed historical bundles remain loadable.
    """
    rows: list[dict[str, Any]] = []
    for item in fragments:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append(
                {
                    "id": getattr(item, "id", None),
                    "locator": getattr(item, "locator", None),
                    "parent_fragment_id": getattr(item, "parent_fragment_id", None),
                    "source_record_id": getattr(item, "source_record_id", None),
                    "source_snapshot_id": getattr(item, "source_snapshot_id", None),
                }
            )

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        fid = _strip(row.get("id") or row.get("fragment_id"))
        if fid:
            by_id[fid] = row

    diagnostics: list[dict[str, Any]] = []

    for row in rows:
        child_id = _strip(row.get("id") or row.get("fragment_id"))
        parent_id = _strip(row.get("parent_fragment_id"))
        if not parent_id:
            continue
        child_locator = _strip(row.get("locator"))
        child_source = _strip(row.get("source_record_id"))
        child_snap = _strip(row.get("source_snapshot_id"))

        if parent_id == child_id:
            diagnostics.append(
                {
                    "code": "source_fragment_parent_not_structural_ancestor",
                    "fragment_id": child_id or None,
                    "parent_fragment_id": parent_id,
                    "locator": child_locator or None,
                    "parent_locator": child_locator or None,
                    "message": "Fragment is its own parent",
                }
            )
            continue

        parent = by_id.get(parent_id)
        if parent is None:
            diagnostics.append(
                {
                    "code": "source_fragment_parent_missing",
                    "fragment_id": child_id or None,
                    "parent_fragment_id": parent_id,
                    "locator": child_locator or None,
                    "message": "Parent fragment id is not present in the fragment set",
                }
            )
            continue

        parent_locator = _strip(parent.get("locator"))
        parent_source = _strip(parent.get("source_record_id"))
        parent_snap = _strip(parent.get("source_snapshot_id"))

        if (child_source and parent_source and child_source != parent_source) or (
            child_snap and parent_snap and child_snap != parent_snap
        ):
            diagnostics.append(
                {
                    "code": "source_fragment_parent_scope_mismatch",
                    "fragment_id": child_id or None,
                    "parent_fragment_id": parent_id,
                    "locator": child_locator or None,
                    "parent_locator": parent_locator or None,
                    "message": "Parent and child are not in the same source record/snapshot scope",
                }
            )
            continue

        if not is_valid_structural_parent(
            parent_locator=parent_locator,
            child_locator=child_locator,
            parent_source_record_id=parent_source,
            child_source_record_id=child_source,
            parent_snapshot_id=parent_snap,
            child_snapshot_id=child_snap,
            parent_id=parent_id,
            child_id=child_id,
        ):
            diagnostics.append(
                {
                    "code": "source_fragment_parent_not_structural_ancestor",
                    "fragment_id": child_id or None,
                    "parent_fragment_id": parent_id,
                    "locator": child_locator or None,
                    "parent_locator": parent_locator or None,
                    "message": "Parent locator is not a structural ancestor of the child",
                }
            )

    # Cycle detection (bounded).
    for row in rows:
        start_id = _strip(row.get("id") or row.get("fragment_id"))
        if not start_id:
            continue
        seen: set[str] = set()
        current = start_id
        while current and current not in seen:
            seen.add(current)
            parent_row = by_id.get(current)
            if parent_row is None:
                break
            next_id = _strip(parent_row.get("parent_fragment_id"))
            if not next_id:
                break
            if next_id == start_id or next_id in seen:
                diagnostics.append(
                    {
                        "code": "source_fragment_parent_cycle",
                        "fragment_id": start_id,
                        "parent_fragment_id": next_id,
                        "locator": _strip(row.get("locator")) or None,
                        "message": "Fragment parent chain contains a cycle",
                    }
                )
                break
            current = next_id

    # Deterministic order for lint stability.
    diagnostics.sort(
        key=lambda item: (
            _strip(item.get("code")),
            _strip(item.get("fragment_id")),
            _strip(item.get("parent_fragment_id")),
            _strip(item.get("locator")),
        )
    )
    return diagnostics
