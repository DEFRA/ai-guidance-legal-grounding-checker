"""Prefer extracting structural child fragments over fully covered parents.

When legislation is split into a container fragment (e.g. ``article:49a``) and
operative child fragments (``article:49a:paragraph:1`` …), both levels can match
focus/selection rules. Extracting the parent then duplicates child propositions
and often merges multi-sentence paragraphs.

Rule
----
After ordinary per-fragment selection, suppress a **selected** parent when:

1. it has one or more substantive direct children;
2. every such child that is needed for coverage is itself selected; and
3. those selected children's texts collectively cover the parent's operative text
   under a conservative normalized containment check.

Parents remain in ``source_fragments`` for navigation, locator context, evidence,
and audit. Only the extraction *selection* flag changes.

Coverage check (conservative)
-----------------------------
Normalize whitespace/case/dashes and strip a leading instrument heading. Then
remove each selected child's normalized text from the parent (exact substring
match after normalization). The parent is covered only when the residual is empty
or consists solely of structural labels/punctuation.

Limitations (intentionally deferred)
------------------------------------
- Does **not** suppress when child text is not a near-verbatim substring of the
  parent (serialization drift, paraphrased slices, partial spans).
- Uses **direct** children only (not deeper descendants).
- Does **not** override ``required_locator`` selection on the parent.
- Does **not** attempt residual-only extraction of uncovered parent prose.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from law_proposition_extractor_domain import SourceFragment

_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_HEADING_RE = re.compile(
    r"^(?:article|regulation|section|rule|schedule|annex|part|chapter)"
    r"\s+[0-9a-z]+[a-z]?\s*\.?\s*",
    re.IGNORECASE,
)
_STRUCTURAL_RESIDUAL_RE = re.compile(
    r"(?:"
    r"article|regulation|section|rule|schedule|annex|part|chapter"
    r"|paragraph|subparagraph|point"
    r"|\([0-9ivxlcdm]+\)"
    r"|[0-9ivxlcdm]+"
    r"|[.\-–,;:()/]"
    r"|\s"
    r")+",
    re.IGNORECASE,
)

SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED = "skipped_structural_children_preferred"
SKIP_REASON_COVERED_BY_SELECTED_CHILDREN = "covered_by_selected_children"

# Focus-match basis values grounded in runner._focus_match_strength.
FOCUS_MATCH_BASIS_MULTIWORD_TERM = "multiword_term"
FOCUS_MATCH_BASIS_MULTIPLE_TERMS = "multiple_terms"
FOCUS_MATCH_BASIS_SINGLE_TERM = "single_term"


@dataclass(frozen=True)
class FocusMatchResult:
    """Immutable focus-term match evidence from one matcher evaluation."""

    strong: bool
    strength: int
    matched_terms: tuple[str, ...]
    basis: str | None = None


@dataclass(frozen=True)
class FragmentSelectionDecision:
    """Per-job selection outcome before/after structural preference."""

    source_record_id: str
    fragment: SourceFragment | None
    selected: bool
    selection_reason: str
    skip_reason: str | None
    fragment_locator: str
    fragment_type: str
    fragment_text_length: int
    # Audit fields populated by structural extraction-frontier preference.
    original_selection_reason: str | None = None
    preferred_ancestor_fragment_id: str | None = None
    preferred_ancestor_locator: str | None = None
    coverage_basis: str | None = None
    selection_diagnostics: tuple[str, ...] = ()
    # Audit-only focus-match evidence captured at ordinary selection time.
    # None means absent (not applicable / not retained); never fabricate.
    matched_focus_terms: tuple[str, ...] | None = None
    focus_match_strength: int | None = None
    focus_match_basis: str | None = None


def normalize_operative_coverage_text(text: str) -> str:
    """Normalize fragment text for conservative parent/child coverage comparison."""
    body = str(text or "").replace("\u00a0", " ")
    body = body.replace("—", "-").replace("–", "-").replace("−", "-")
    body = _WHITESPACE_RE.sub(" ", body).strip().lower()
    body = _LEADING_HEADING_RE.sub("", body, count=1).strip()
    return _WHITESPACE_RE.sub(" ", body).strip()


def _residual_is_non_operative(residual: str) -> bool:
    if not residual:
        return True
    stripped = _STRUCTURAL_RESIDUAL_RE.sub("", residual)
    return stripped == ""


def children_cover_parent_operative_text(
    parent_text: str,
    child_texts: list[str],
) -> bool:
    """Return True only when selected children reliably cover the parent body.

    Requires every supplied child text to appear as a normalized substring of the
    parent, and the residual after removal to be empty/structural-only.

    A single small substring match is never enough: all provided children must
    match, and the residual must not retain operative prose.
    """
    if not child_texts:
        return False
    residual = normalize_operative_coverage_text(parent_text)
    if not residual:
        return False
    normalized_children: list[str] = []
    for child in child_texts:
        child_norm = normalize_operative_coverage_text(child)
        if not child_norm:
            return False
        normalized_children.append(child_norm)
    # Reject trivial "coverage" where one short child is a tiny slice of parent.
    parent_len = len(residual)
    total_child_len = sum(len(c) for c in normalized_children)
    if parent_len > 0 and total_child_len < max(24, int(parent_len * 0.5)):
        return False
    for child_norm in normalized_children:
        if child_norm not in residual:
            return False
        residual = residual.replace(child_norm, " ", 1)
        residual = _WHITESPACE_RE.sub(" ", residual).strip()
    return _residual_is_non_operative(residual)


def _fragment_sort_key(fragment: SourceFragment) -> tuple[int, int, str]:
    order = fragment.order_index
    return (order is None, order if order is not None else 0, fragment.id)


def apply_structural_child_extraction_preference(
    decisions: list[FragmentSelectionDecision],
    *,
    is_non_operative_fragment: Callable[[str], bool],
) -> list[FragmentSelectionDecision]:
    """Suppress selected parents fully covered by selected substantive children.

    Input order is preserved. When coverage is uncertain, decisions are unchanged.
    """
    if not decisions:
        return []

    by_source: dict[str, list[int]] = {}
    for idx, decision in enumerate(decisions):
        by_source.setdefault(decision.source_record_id, []).append(idx)

    out = list(decisions)
    for source_id in sorted(by_source):
        indexes = by_source[source_id]
        fragments = [
            out[i].fragment
            for i in indexes
            if out[i].fragment is not None
        ]
        if not fragments:
            continue
        by_id = {frag.id: frag for frag in fragments if frag is not None}
        children_by_parent: dict[str, list[SourceFragment]] = {}
        for frag in fragments:
            assert frag is not None
            parent_id = str(frag.parent_fragment_id or "").strip()
            if not parent_id or parent_id not in by_id:
                continue
            children_by_parent.setdefault(parent_id, []).append(frag)

        decision_by_fragment_id = {
            out[i].fragment.id: i
            for i in indexes
            if out[i].fragment is not None
        }

        parent_ids = sorted(
            children_by_parent,
            key=lambda pid: _fragment_sort_key(by_id[pid]),
        )
        for parent_id in parent_ids:
            parent_idx = decision_by_fragment_id.get(parent_id)
            if parent_idx is None:
                continue
            parent_decision = out[parent_idx]
            if not parent_decision.selected:
                continue
            # Explicit required locators stay selected even if children cover them.
            if parent_decision.selection_reason == "required_locator":
                continue
            parent_frag = parent_decision.fragment
            if parent_frag is None:
                continue
            if is_non_operative_fragment(parent_decision.fragment_type):
                continue

            direct_children = sorted(children_by_parent[parent_id], key=_fragment_sort_key)
            selected_substantive_children: list[SourceFragment] = []
            for child in direct_children:
                child_idx = decision_by_fragment_id.get(child.id)
                if child_idx is None:
                    continue
                child_decision = out[child_idx]
                if not child_decision.selected:
                    continue
                if is_non_operative_fragment(child_decision.fragment_type):
                    continue
                selected_substantive_children.append(child)

            if not selected_substantive_children:
                continue

            # Require that every substantive direct child is selected before
            # treating coverage as reliable. Unselected siblings leave uncertainty
            # about whether parent residual would still need extraction.
            substantive_direct = [
                child
                for child in direct_children
                if not is_non_operative_fragment(
                    str(child.fragment_type or "unknown")
                )
            ]
            if len(selected_substantive_children) != len(substantive_direct):
                continue

            covered = children_cover_parent_operative_text(
                parent_frag.fragment_text,
                [child.fragment_text for child in selected_substantive_children],
            )
            if not covered:
                continue

            out[parent_idx] = replace(
                parent_decision,
                selected=False,
                original_selection_reason=(
                    parent_decision.original_selection_reason
                    or parent_decision.selection_reason
                ),
                selection_reason=SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED,
                skip_reason=SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
            )
    return out
