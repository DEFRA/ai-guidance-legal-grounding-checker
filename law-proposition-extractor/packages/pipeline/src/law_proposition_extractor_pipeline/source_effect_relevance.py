"""Capture source-effect relevance facts for DecisionExplanation emission.

Matches stored SourceLegalEffect links to statements using the same structural
rules as the Workbench projection. Does not re-parse CLML or re-run amendment
application. Facts are captured once at attach time; explanation builders map
facts to DecisionExplanation records without re-matching.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from law_proposition_extractor_pipeline.source_fragment_hierarchy import (
    is_locator_structural_ancestor,
    is_top_level_provision_locator,
    is_valid_structural_parent,
)

FACT_LINK_EXACT = "link_exact_fragment"
FACT_INHERIT_ANCESTOR = "inherit_from_structural_ancestor"
FACT_EXCLUDE_UNRELATED = "exclude_unrelated_fragment"


def _trim(value: Any) -> str:
    return str(value or "").strip()


def _root_provision_locator(locator: str) -> str | None:
    text = _trim(locator).lower()
    if not text:
        return None
    parts = [p for p in text.split(":") if p]
    if len(parts) >= 2 and parts[0] in {
        "article",
        "regulation",
        "rule",
        "section",
        "annex",
        "schedule",
    }:
        return f"{parts[0]}:{parts[1]}"
    return None


def _fragment_row_id(row: Mapping[str, Any]) -> str:
    return _trim(row.get("id"))


def _ancestor_path(
    fragment_id: str | None,
    fragment_by_id: dict[str, Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    """Return (ancestor_fragment_ids, validated_parent_path_locators)."""
    ancestors: list[str] = []
    path_locs: list[str] = []
    seen: set[str] = set()
    current = _trim(fragment_id) or None
    while current and current not in seen:
        seen.add(current)
        row = fragment_by_id.get(current)
        if row is None:
            break
        parent_id = _trim(row.get("parent_fragment_id")) or None
        if not parent_id:
            break
        parent = fragment_by_id.get(parent_id)
        if parent is None:
            break
        if not is_valid_structural_parent(
            parent_locator=_trim(parent.get("locator")) or None,
            child_locator=_trim(row.get("locator")) or None,
            parent_source_record_id=_trim(parent.get("source_record_id")) or None,
            child_source_record_id=_trim(row.get("source_record_id")) or None,
            parent_snapshot_id=_trim(parent.get("source_snapshot_id")) or None,
            child_snapshot_id=_trim(row.get("source_snapshot_id")) or None,
            parent_id=parent_id,
            child_id=current,
        ):
            # Defensive stop on invalid legacy edges — do not traverse.
            break
        ancestors.append(parent_id)
        parent_loc = _trim(parent.get("locator"))
        if parent_loc:
            path_locs.append(parent_loc)
        current = parent_id
    return ancestors, path_locs


def _links_for(
    effect_id: str,
    links: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [lnk for lnk in links if _trim(lnk.get("effect_id")) == effect_id]


def _match_effect_to_proposition(
    *,
    effect: Mapping[str, Any],
    links: Sequence[Mapping[str, Any]],
    fragment_id: str | None,
    locator: str | None,
    ancestor_ids: set[str],
) -> dict[str, Any] | None:
    """Return best match dict or None.

    When the effect's primary ``affected_locator`` is a proper structural ancestor
    of the receiving locator, prefer ``structural_ancestor`` even if descendant
    links also exist (article-level annotations shown on paragraphs).
    Otherwise prefer exact fragment/locator matches over ancestor matches.
    """
    effect_id = _trim(effect.get("id"))
    effect_links = _links_for(effect_id, links)
    primary_locator = _trim(effect.get("affected_locator")) or None
    primary_fragment = _trim(effect.get("affected_source_fragment_id")) or None

    # Top-level provision primary attachment (e.g. article:49a) → inherit to
    # descendants even when descendant links also exist.
    if (
        locator
        and primary_locator
        and is_top_level_provision_locator(primary_locator)
        and is_locator_structural_ancestor(primary_locator, locator)
    ):
        link_id = None
        for link in effect_links:
            if _trim(link.get("affected_locator")) == primary_locator or (
                primary_fragment and _trim(link.get("source_fragment_id")) == primary_fragment
            ):
                link_id = _trim(link.get("id")) or None
                break
        return {
            "relevance_basis": "structural_ancestor",
            "effect_link_id": link_id,
            "linked_fragment_id": fragment_id,
            "linked_locator": locator,
            "ancestor_fragment_id": primary_fragment,
            "ancestor_locator": primary_locator,
        }

    best: dict[str, Any] | None = None

    def consider(candidate: dict[str, Any]) -> None:
        nonlocal best
        if best is None:
            best = candidate
            return
        if candidate["relevance_basis"] == "exact_fragment" and best[
            "relevance_basis"
        ] != "exact_fragment":
            best = candidate

    for link in effect_links:
        link_fragment_id = _trim(link.get("source_fragment_id")) or None
        link_locator = _trim(link.get("affected_locator")) or None
        link_id = _trim(link.get("id")) or None

        if fragment_id and link_fragment_id and link_fragment_id == fragment_id:
            consider(
                {
                    "relevance_basis": "exact_fragment",
                    "effect_link_id": link_id,
                    "linked_fragment_id": link_fragment_id,
                    "linked_locator": link_locator or locator,
                    "ancestor_fragment_id": None,
                    "ancestor_locator": None,
                }
            )
            continue

        if locator and link_locator and link_locator == locator:
            consider(
                {
                    "relevance_basis": "exact_fragment",
                    "effect_link_id": link_id,
                    "linked_fragment_id": link_fragment_id,
                    "linked_locator": link_locator,
                    "ancestor_fragment_id": None,
                    "ancestor_locator": None,
                }
            )
            continue

        if fragment_id and link_fragment_id and link_fragment_id in ancestor_ids:
            consider(
                {
                    "relevance_basis": "structural_ancestor",
                    "effect_link_id": link_id,
                    "linked_fragment_id": fragment_id,
                    "linked_locator": locator,
                    "ancestor_fragment_id": link_fragment_id,
                    "ancestor_locator": link_locator,
                }
            )
            continue

        if locator and link_locator and is_locator_structural_ancestor(link_locator, locator):
            consider(
                {
                    "relevance_basis": "structural_ancestor",
                    "effect_link_id": link_id,
                    "linked_fragment_id": fragment_id,
                    "linked_locator": locator,
                    "ancestor_fragment_id": link_fragment_id,
                    "ancestor_locator": link_locator,
                }
            )

    if best is not None:
        return best

    # Fallback: effect-level fragment / locator when links are sparse.
    effect_fragment_id = primary_fragment
    effect_locator = primary_locator
    if fragment_id and effect_fragment_id and effect_fragment_id == fragment_id:
        return {
            "relevance_basis": "exact_fragment",
            "effect_link_id": None,
            "linked_fragment_id": effect_fragment_id,
            "linked_locator": effect_locator or locator,
            "ancestor_fragment_id": None,
            "ancestor_locator": None,
        }
    if locator and effect_locator and effect_locator == locator:
        return {
            "relevance_basis": "exact_fragment",
            "effect_link_id": None,
            "linked_fragment_id": effect_fragment_id,
            "linked_locator": effect_locator,
            "ancestor_fragment_id": None,
            "ancestor_locator": None,
        }
    if fragment_id and effect_fragment_id and effect_fragment_id in ancestor_ids:
        return {
            "relevance_basis": "structural_ancestor",
            "effect_link_id": None,
            "linked_fragment_id": fragment_id,
            "linked_locator": locator,
            "ancestor_fragment_id": effect_fragment_id,
            "ancestor_locator": effect_locator,
        }
    if locator and effect_locator and is_locator_structural_ancestor(effect_locator, locator):
        return {
            "relevance_basis": "structural_ancestor",
            "effect_link_id": None,
            "linked_fragment_id": fragment_id,
            "linked_locator": locator,
            "ancestor_fragment_id": effect_fragment_id,
            "ancestor_locator": effect_locator,
        }
    return None


def _effect_top_level_locator(
    effect: Mapping[str, Any],
    links: Sequence[Mapping[str, Any]],
) -> str | None:
    for link in _links_for(_trim(effect.get("id")), links):
        loc = _trim(link.get("affected_locator"))
        if loc and is_top_level_provision_locator(loc):
            return loc
        root = _root_provision_locator(loc)
        if root and is_top_level_provision_locator(root) and loc == root:
            return loc
    loc = _trim(effect.get("affected_locator"))
    if loc and is_top_level_provision_locator(loc):
        return loc
    return None


def capture_source_effect_relevance_facts(
    *,
    statements: Sequence[Mapping[str, Any]],
    propositions: Sequence[Mapping[str, Any]],
    fragments: Sequence[Mapping[str, Any]],
    effects: Sequence[Mapping[str, Any]],
    effect_links: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Capture exact/inherit/exclude relevance facts for statement subjects.

    Duplicate links for the same (statement, effect, basis) collapse to one fact.
    """
    prop_by_id = {
        _trim(p.get("id")): p
        for p in propositions
        if isinstance(p, Mapping) and _trim(p.get("id"))
    }
    fragment_by_id = {
        _fragment_row_id(f): f
        for f in fragments
        if isinstance(f, Mapping) and _fragment_row_id(f)
    }

    facts: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(fact: dict[str, Any]) -> None:
        key = "|".join(
            (
                str(fact.get("fact_kind") or ""),
                str(fact.get("effective_law_statement_id") or ""),
                str(fact.get("effect_id") or ""),
                str(fact.get("relevance_basis") or ""),
                str(fact.get("outcome") or ""),
            )
        )
        if key in seen:
            return
        seen.add(key)
        facts.append(fact)

    for stmt in statements:
        if not isinstance(stmt, Mapping):
            continue
        stmt_id = _trim(stmt.get("id"))
        if not stmt_id:
            continue
        source_prop_ids = [
            _trim(pid)
            for pid in (stmt.get("source_proposition_ids") or [])
            if _trim(pid)
        ]
        if not source_prop_ids:
            continue
        # Prefer primary / first proposition for fragment identity.
        prop = prop_by_id.get(source_prop_ids[0])
        if prop is None:
            continue

        source_record_id = _trim(prop.get("source_record_id"))
        snapshot_id = _trim(prop.get("source_snapshot_id"))
        fragment_id = _trim(prop.get("source_fragment_id")) or None
        fragment = fragment_by_id.get(fragment_id) if fragment_id else None
        locator = (
            _trim(prop.get("fragment_locator"))
            or (_trim(fragment.get("locator")) if fragment else "")
            or None
        )
        if not source_record_id or not snapshot_id:
            continue

        ancestor_ids_list, parent_path = _ancestor_path(fragment_id, fragment_by_id)
        ancestor_ids = set(ancestor_ids_list)
        receiving_root = _root_provision_locator(locator or "")

        scoped_effects = [
            e
            for e in effects
            if isinstance(e, Mapping)
            and _trim(e.get("source_record_id")) == source_record_id
            and _trim(e.get("source_snapshot_id")) == snapshot_id
        ]
        scoped_links = [
            lnk
            for lnk in effect_links
            if isinstance(lnk, Mapping)
            and _trim(lnk.get("source_record_id")) == source_record_id
            and _trim(lnk.get("source_snapshot_id")) == snapshot_id
        ]

        for effect in scoped_effects:
            effect_id = _trim(effect.get("id"))
            if not effect_id:
                continue
            match = _match_effect_to_proposition(
                effect=effect,
                links=scoped_links,
                fragment_id=fragment_id,
                locator=locator,
                ancestor_ids=ancestor_ids,
            )
            if match is not None:
                basis = match["relevance_basis"]
                if basis == "exact_fragment":
                    add(
                        {
                            "fact_kind": FACT_LINK_EXACT,
                            "outcome": "source_effect_relevant",
                            "effective_law_statement_id": stmt_id,
                            "receiving_proposition_id": source_prop_ids[0],
                            "effect_id": effect_id,
                            "effect_link_id": match.get("effect_link_id"),
                            "annotation_id": effect.get("annotation_id"),
                            "annotation_label": effect.get("annotation_label"),
                            "effect_category": (
                                effect.get("effect_category")
                                if not hasattr(effect.get("effect_category"), "value")
                                else effect.get("effect_category")
                            ),
                            "source_record_id": source_record_id,
                            "source_snapshot_id": snapshot_id,
                            "linked_fragment_id": match.get("linked_fragment_id"),
                            "linked_locator": match.get("linked_locator"),
                            "relevance_basis": "exact_fragment",
                            "affected_locator": effect.get("affected_locator"),
                        }
                    )
                else:
                    add(
                        {
                            "fact_kind": FACT_INHERIT_ANCESTOR,
                            "outcome": "source_effect_relevant",
                            "effective_law_statement_id": stmt_id,
                            "receiving_proposition_id": source_prop_ids[0],
                            "effect_id": effect_id,
                            "effect_link_id": match.get("effect_link_id"),
                            "annotation_id": effect.get("annotation_id"),
                            "annotation_label": effect.get("annotation_label"),
                            "source_record_id": source_record_id,
                            "source_snapshot_id": snapshot_id,
                            "ancestor_fragment_id": match.get("ancestor_fragment_id"),
                            "ancestor_locator": match.get("ancestor_locator"),
                            "descendant_fragment_id": fragment_id,
                            "descendant_locator": locator,
                            "validated_parent_path": list(parent_path),
                            "relevance_basis": "structural_ancestor",
                            "affected_locator": effect.get("affected_locator"),
                        }
                    )
                continue

            # Focused exclusion: unrelated top-level provision branch.
            top_loc = _effect_top_level_locator(effect, scoped_links)
            if not top_loc or not receiving_root:
                continue
            effect_root = _root_provision_locator(top_loc)
            if not effect_root or effect_root == receiving_root:
                continue
            if is_locator_structural_ancestor(top_loc, locator or ""):
                continue
            add(
                {
                    "fact_kind": FACT_EXCLUDE_UNRELATED,
                    "outcome": "source_effect_excluded",
                    "effective_law_statement_id": stmt_id,
                    "receiving_proposition_id": source_prop_ids[0],
                    "effect_id": effect_id,
                    "annotation_id": effect.get("annotation_id"),
                    "annotation_label": effect.get("annotation_label"),
                    "source_record_id": source_record_id,
                    "source_snapshot_id": snapshot_id,
                    "effect_fragment_locator": top_loc,
                    "receiving_locator": locator,
                    "receiving_root_provision": receiving_root,
                    "effect_root_provision": effect_root,
                    "relevance_basis": "unrelated_fragment",
                    "reason": (
                        f"{effect_root} is not a structural ancestor of "
                        f"{receiving_root}"
                    ),
                }
            )

    facts.sort(
        key=lambda f: (
            str(f.get("fact_kind") or ""),
            str(f.get("effective_law_statement_id") or ""),
            str(f.get("effect_id") or ""),
            str(f.get("relevance_basis") or ""),
        )
    )
    return facts
