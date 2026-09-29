"""Prefer required ancestors over opportunistic focus-selected descendants.

When an explicitly required structural ancestor is selected for extraction and a
descendant is selected only via opportunistic focus matching, extracting both
duplicates operative content already covered by the ancestor (e.g. Article 49a
paragraph 2 vs focus-matched subparagraph (a)).

Rule
----
After ordinary selection and structural-child preference, suppress a **selected**
descendant when:

1. ancestor and descendant share the same source record and snapshot;
2. the ancestor is a genuine structural ancestor via ``parent_fragment_id``;
3. the ancestor is selected through ``required_locator``;
4. the descendant is selected only through an opportunistic reason
   (currently ``focus_term_match``);
5. descendant operative text is contained in the ancestor; and
6. the ancestor extraction path is expected to cover the descendant
   (text containment under a required ancestor, and/or structured-list drafts
   that cover the descendant's terminal markers).

Explicitly required descendants are never suppressed merely because an ancestor
is also required. Overlaps that cannot be resolved safely emit a non-blocking
``selected_structural_overlap_unresolved`` diagnostic.
"""

from __future__ import annotations

import re
from dataclasses import replace

from law_proposition_extractor_domain import SourceFragment

from .structural_child_extraction_preference import (
    FragmentSelectionDecision,
    normalize_operative_coverage_text,
)
from .structured_list_decomposition import draft_structured_list_leaves

SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED = "skipped_required_ancestor_preferred"
SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR = "covered_by_required_ancestor"
COVERAGE_BASIS_TEXT_CONTAINED = "structural_descendant_text_contained"
COVERAGE_BASIS_STRUCTURED_LIST = "structured_list_ancestor_covers_descendant"
DIAGNOSTIC_UNRESOLVED_OVERLAP = "selected_structural_overlap_unresolved"

EXPLICIT_SELECTION_REASONS = frozenset({"required_locator"})
OPPORTUNISTIC_SELECTION_REASONS = frozenset({"focus_term_match"})

_SUBPARAGRAPH_LETTER_RE = re.compile(r"subparagraph:([a-z])\b", re.IGNORECASE)
_PATH_LETTER_RE = re.compile(r"(?:^|-)([a-z])(?:-|$)")


def _fragment_sort_key(fragment: SourceFragment) -> tuple[int, int, str]:
    order = fragment.order_index
    return (order is None, order if order is not None else 0, fragment.id)


def _same_source_snapshot(a: SourceFragment, b: SourceFragment) -> bool:
    return (
        str(a.source_record_id) == str(b.source_record_id)
        and str(a.source_snapshot_id) == str(b.source_snapshot_id)
    )


def _ancestor_chain(
    fragment: SourceFragment,
    by_id: dict[str, SourceFragment],
) -> list[SourceFragment]:
    """Return structural ancestors nearest-first; stop on broken/cross links."""
    chain: list[SourceFragment] = []
    seen: set[str] = {fragment.id}
    current = fragment
    while True:
        parent_id = str(current.parent_fragment_id or "").strip()
        if not parent_id or parent_id not in by_id or parent_id in seen:
            break
        parent = by_id[parent_id]
        if not _same_source_snapshot(fragment, parent):
            break
        chain.append(parent)
        seen.add(parent_id)
        current = parent
    return chain


def descendant_text_contained_in_ancestor(
    ancestor_text: str,
    descendant_text: str,
) -> bool:
    """True when normalized descendant body is a non-empty substring of ancestor."""
    ancestor_norm = normalize_operative_coverage_text(ancestor_text)
    descendant_norm = normalize_operative_coverage_text(descendant_text)
    if not ancestor_norm or not descendant_norm:
        return False
    return descendant_norm in ancestor_norm


def structured_list_ancestor_covers_descendant(
    ancestor_text: str,
    ancestor_locator: str,
    descendant_text: str,
    descendant_locator: str,
) -> bool:
    """True when ancestor structured-list drafts cover the descendant terminals."""
    drafts = draft_structured_list_leaves(ancestor_text, ancestor_locator)
    if not drafts:
        return False

    letter_match = _SUBPARAGRAPH_LETTER_RE.search(str(descendant_locator or ""))
    if letter_match:
        letter = letter_match.group(1).lower()
        matching = [
            draft
            for draft in drafts
            if any(
                token == letter
                for token in _PATH_LETTER_RE.findall(str(draft.path_key or "").lower())
            )
        ]
        if matching:
            return True

    descendant_norm = normalize_operative_coverage_text(descendant_text)
    if not descendant_norm:
        return False
    for draft in drafts:
        draft_blob = normalize_operative_coverage_text(
            " ".join(
                part
                for part in (
                    draft.parent_intro,
                    draft.branch_context,
                    draft.item_tail,
                    draft.standalone_text,
                )
                if part
            )
        )
        if descendant_norm in draft_blob or draft_blob in descendant_norm:
            return True
        # Branch body alone often equals a subparagraph fragment.
        branch_norm = normalize_operative_coverage_text(draft.branch_context)
        if branch_norm and (
            descendant_norm in branch_norm or branch_norm in descendant_norm
        ):
            return True
    return False


def establish_ancestor_coverage(
    ancestor: SourceFragment,
    descendant: SourceFragment,
) -> str | None:
    """Return coverage_basis when the ancestor can safely cover the descendant."""
    text_contained = descendant_text_contained_in_ancestor(
        ancestor.fragment_text,
        descendant.fragment_text,
    )
    if not text_contained:
        return None

    if structured_list_ancestor_covers_descendant(
        ancestor.fragment_text,
        ancestor.locator,
        descendant.fragment_text,
        descendant.locator,
    ):
        return COVERAGE_BASIS_STRUCTURED_LIST

    # Required ancestor + full text containment is sufficient coverage evidence.
    return COVERAGE_BASIS_TEXT_CONTAINED


def apply_required_ancestor_extraction_frontier(
    decisions: list[FragmentSelectionDecision],
) -> list[FragmentSelectionDecision]:
    """Suppress focus-only descendants covered by selected required ancestors.

    Input order is preserved. When coverage or hierarchy is uncertain, decisions
    are left unchanged (fail-closed / conservative).
    """
    if not decisions:
        return []

    out = list(decisions)
    by_source_snapshot: dict[tuple[str, str], list[int]] = {}
    for idx, decision in enumerate(out):
        frag = decision.fragment
        if frag is None:
            continue
        key = (str(frag.source_record_id), str(frag.source_snapshot_id))
        by_source_snapshot.setdefault(key, []).append(idx)

    for snapshot_indexes in by_source_snapshot.values():
        fragments = [
            out[i].fragment
            for i in snapshot_indexes
            if out[i].fragment is not None
        ]
        by_id = {frag.id: frag for frag in fragments if frag is not None}
        decision_by_fragment_id = {
            out[i].fragment.id: i
            for i in snapshot_indexes
            if out[i].fragment is not None
        }

        # Deterministic descendant walk: stable fragment order.
        candidate_indexes = sorted(
            snapshot_indexes,
            key=lambda i: _fragment_sort_key(out[i].fragment)  # type: ignore[arg-type]
            if out[i].fragment is not None
            else (True, 0, ""),
        )

        for desc_idx in candidate_indexes:
            desc_decision = out[desc_idx]
            if not desc_decision.selected:
                continue
            desc_frag = desc_decision.fragment
            if desc_frag is None:
                continue

            reason = str(desc_decision.selection_reason or "")
            ancestors = _ancestor_chain(desc_frag, by_id)
            if not ancestors:
                continue

            # Explicit required descendant under required ancestor: keep both,
            # emit unresolved-overlap diagnostic when text is nested.
            if reason in EXPLICIT_SELECTION_REASONS:
                for ancestor in ancestors:
                    anc_idx = decision_by_fragment_id.get(ancestor.id)
                    if anc_idx is None:
                        continue
                    anc_decision = out[anc_idx]
                    if not anc_decision.selected:
                        continue
                    if anc_decision.selection_reason not in EXPLICIT_SELECTION_REASONS:
                        continue
                    if not descendant_text_contained_in_ancestor(
                        ancestor.fragment_text,
                        desc_frag.fragment_text,
                    ):
                        continue
                    diag = DIAGNOSTIC_UNRESOLVED_OVERLAP
                    if diag not in desc_decision.selection_diagnostics:
                        out[desc_idx] = replace(
                            desc_decision,
                            selection_diagnostics=tuple(
                                dict.fromkeys(
                                    (*desc_decision.selection_diagnostics, diag)
                                )
                            ),
                            preferred_ancestor_fragment_id=ancestor.id,
                            preferred_ancestor_locator=ancestor.locator,
                            original_selection_reason=(
                                desc_decision.original_selection_reason or reason
                            ),
                        )
                        desc_decision = out[desc_idx]
                    if diag not in anc_decision.selection_diagnostics:
                        out[anc_idx] = replace(
                            anc_decision,
                            selection_diagnostics=tuple(
                                dict.fromkeys(
                                    (*anc_decision.selection_diagnostics, diag)
                                )
                            ),
                        )
                continue

            if reason not in OPPORTUNISTIC_SELECTION_REASONS:
                continue

            covering: tuple[SourceFragment, FragmentSelectionDecision, str] | None = None
            for ancestor in ancestors:
                anc_idx = decision_by_fragment_id.get(ancestor.id)
                if anc_idx is None:
                    continue
                anc_decision = out[anc_idx]
                if not anc_decision.selected:
                    continue
                if anc_decision.selection_reason not in EXPLICIT_SELECTION_REASONS:
                    continue
                coverage_basis = establish_ancestor_coverage(ancestor, desc_frag)
                if coverage_basis is None:
                    continue
                covering = (ancestor, anc_decision, coverage_basis)
                break  # nearest covering required ancestor

            if covering is None:
                continue

            ancestor, _anc_decision, coverage_basis = covering
            out[desc_idx] = replace(
                desc_decision,
                selected=False,
                original_selection_reason=reason,
                selection_reason=SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED,
                skip_reason=SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
                preferred_ancestor_fragment_id=ancestor.id,
                preferred_ancestor_locator=ancestor.locator,
                coverage_basis=coverage_basis,
            )

    return out
