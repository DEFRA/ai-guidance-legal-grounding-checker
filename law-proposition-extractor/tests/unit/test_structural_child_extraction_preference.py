"""Structural child preference for extraction selection (Article 49a-shaped)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import SourceFragment, SourceRecord
from law_proposition_extractor_pipeline.runner import (
    _build_extraction_selection_decisions,
    _is_non_operative_fragment,
)
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED,
    FragmentSelectionDecision,
    apply_structural_child_extraction_preference,
    children_cover_parent_operative_text,
    normalize_operative_coverage_text,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)


def _load_49a_fragments() -> list[SourceFragment]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    source_id = str(payload["source_record_id"])
    snapshot_id = str(payload["source_snapshot_id"])
    fragments: list[SourceFragment] = []
    for row in payload["fragments"]:
        text = str(row["fragment_text"])
        fragments.append(
            SourceFragment(
                id=str(row["id"]),
                source_record_id=source_id,
                source_snapshot_id=snapshot_id,
                locator=str(row["locator"]),
                fragment_type=str(row.get("fragment_type") or "article"),
                fragment_text=text,
                fragment_hash=f"hash-{row['id']}",
                parent_fragment_id=row.get("parent_fragment_id"),
                order_index=row.get("order_index"),
            )
        )
    return fragments


def _source_record(source_id: str = "src-control-regulation-demo") -> SourceRecord:
    return SourceRecord(
        id=source_id,
        title="Demo control regulation",
        jurisdiction="UK",
        citation="DEMO/1224",
        kind="regulation",
        authoritative_text="unused",
        authoritative_locator="document:full",
        current_snapshot_id="snap-src-control-regulation-demo-v1",
    )


def _decision_for(
    fragment: SourceFragment,
    *,
    selected: bool,
    reason: str = "focus_term_match",
    skip_reason: str | None = None,
) -> FragmentSelectionDecision:
    return FragmentSelectionDecision(
        source_record_id=fragment.source_record_id,
        fragment=fragment,
        selected=selected,
        selection_reason=reason if selected else (reason or "skipped_no_focus_match"),
        skip_reason=None if selected else (skip_reason or "no_focus_match"),
        fragment_locator=fragment.locator,
        fragment_type=fragment.fragment_type,
        fragment_text_length=len(fragment.fragment_text),
    )


def test_normalize_strips_heading_and_whitespace() -> None:
    raw = "Article 49a.\n\n  (1) Catches  shall  be  kept."
    assert normalize_operative_coverage_text(raw) == "(1) catches shall be kept."


def test_children_cover_parent_for_article_49a_shaped_fixture() -> None:
    by_locator = {f.locator: f for f in _load_49a_fragments()}
    parent = by_locator["article:49a"]
    children = [
        by_locator["article:49a:paragraph:1"].fragment_text,
        by_locator["article:49a:paragraph:2"].fragment_text,
        by_locator["article:49a:paragraph:3"].fragment_text,
    ]
    assert children_cover_parent_operative_text(parent.fragment_text, children) is True


def test_small_substring_is_not_full_coverage() -> None:
    parent = "Operators must keep records. Operators must also notify the authority within 24 hours."
    assert children_cover_parent_operative_text(parent, ["Operators must keep records."]) is False


def test_parent_with_uncovered_intro_is_not_covered() -> None:
    parent = (
        "Operators shall notify the authority before landing. "
        "(1) Records must be kept onboard. "
        "(2) Records must be stored ashore."
    )
    children = [
        "(1) Records must be kept onboard.",
        "(2) Records must be stored ashore.",
    ]
    assert children_cover_parent_operative_text(parent, children) is False


def test_covered_parent_suppressed_children_remain_selected() -> None:
    fragments = _load_49a_fragments()
    by_locator = {f.locator: f for f in fragments}
    # Reverse input order to prove determinism of suppression outcome.
    ordered = [
        by_locator["article:49a:paragraph:3"],
        by_locator["article:49a"],
        by_locator["article:49a:paragraph:1"],
        by_locator["document:full"],
        by_locator["article:49a:paragraph:2"],
    ]
    base = [
        _decision_for(by_locator["document:full"], selected=False, reason="skipped_non_operative"),
        _decision_for(by_locator["article:49a"], selected=True),
        _decision_for(by_locator["article:49a:paragraph:1"], selected=True),
        _decision_for(by_locator["article:49a:paragraph:2"], selected=True),
        _decision_for(by_locator["article:49a:paragraph:3"], selected=True),
    ]
    # Rebuild base in reversed fragment presentation order.
    base_by_id = {d.fragment.id: d for d in base if d.fragment is not None}
    reversed_base = [base_by_id[f.id] for f in ordered]

    preferred = apply_structural_child_extraction_preference(
        reversed_base,
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    by_loc = {
        d.fragment_locator: d for d in preferred if d.fragment is not None
    }

    assert by_loc["article:49a"].fragment is not None
    assert by_loc["article:49a"].selected is False
    assert (
        by_loc["article:49a"].selection_reason
        == SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED
    )
    assert by_loc["article:49a"].skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
    assert by_loc["article:49a:paragraph:1"].selected is True
    assert by_loc["article:49a:paragraph:2"].selected is True
    assert by_loc["article:49a:paragraph:3"].selected is True
    # Parent remains in the decision set (fragment collection analogue).
    assert {d.fragment.id for d in preferred if d.fragment is not None} == {
        f.id for f in ordered
    }


def test_parent_with_operative_text_outside_children_not_suppressed() -> None:
    source_id = "src-parent-intro"
    snapshot_id = "snap-parent-intro"
    parent = SourceFragment(
        id="frag-parent",
        source_record_id=source_id,
        source_snapshot_id=snapshot_id,
        locator="article:10",
        fragment_type="article",
        fragment_text=(
            "Operators shall notify the authority before landing. "
            "(1) Records must be kept onboard. "
            "(2) Records must be stored ashore."
        ),
        fragment_hash="h-parent",
        order_index=1,
    )
    child1 = SourceFragment(
        id="frag-p1",
        source_record_id=source_id,
        source_snapshot_id=snapshot_id,
        locator="article:10:paragraph:1",
        fragment_type="article",
        fragment_text="(1) Records must be kept onboard.",
        fragment_hash="h-p1",
        parent_fragment_id=parent.id,
        order_index=2,
    )
    child2 = SourceFragment(
        id="frag-p2",
        source_record_id=source_id,
        source_snapshot_id=snapshot_id,
        locator="article:10:paragraph:2",
        fragment_type="article",
        fragment_text="(2) Records must be stored ashore.",
        fragment_hash="h-p2",
        parent_fragment_id=parent.id,
        order_index=3,
    )
    preferred = apply_structural_child_extraction_preference(
        [
            _decision_for(parent, selected=True),
            _decision_for(child1, selected=True),
            _decision_for(child2, selected=True),
        ],
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    parent_decision = next(d for d in preferred if d.fragment_locator == "article:10")
    assert parent_decision.selected is True
    assert parent_decision.selection_reason == "focus_term_match"


def test_parent_with_no_substantive_children_remains_extractable() -> None:
    source_id = "src-leaf"
    parent = SourceFragment(
        id="frag-leaf",
        source_record_id=source_id,
        source_snapshot_id="snap-leaf",
        locator="article:7",
        fragment_type="article",
        fragment_text="A fisheries administration must publish sampling results annually.",
        fragment_hash="h-leaf",
        order_index=1,
    )
    preferred = apply_structural_child_extraction_preference(
        [_decision_for(parent, selected=True)],
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    assert preferred[0].selected is True
    assert preferred[0].selection_reason == "focus_term_match"


def test_required_locator_parent_not_suppressed_even_when_covered() -> None:
    fragments = _load_49a_fragments()
    by_locator = {f.locator: f for f in fragments}
    preferred = apply_structural_child_extraction_preference(
        [
            _decision_for(
                by_locator["article:49a"],
                selected=True,
                reason="required_locator",
            ),
            _decision_for(by_locator["article:49a:paragraph:1"], selected=True),
            _decision_for(by_locator["article:49a:paragraph:2"], selected=True),
            _decision_for(by_locator["article:49a:paragraph:3"], selected=True),
        ],
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    parent = next(d for d in preferred if d.fragment_locator == "article:49a")
    assert parent.selected is True
    assert parent.selection_reason == "required_locator"


def test_uncertain_coverage_when_not_all_children_selected_preserves_parent() -> None:
    fragments = _load_49a_fragments()
    by_locator = {f.locator: f for f in fragments}
    preferred = apply_structural_child_extraction_preference(
        [
            _decision_for(by_locator["article:49a"], selected=True),
            _decision_for(by_locator["article:49a:paragraph:1"], selected=True),
            _decision_for(by_locator["article:49a:paragraph:2"], selected=False),
            _decision_for(by_locator["article:49a:paragraph:3"], selected=True),
        ],
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    parent = next(d for d in preferred if d.fragment_locator == "article:49a")
    assert parent.selected is True


def test_selection_deterministic_regardless_of_input_order() -> None:
    fragments = _load_49a_fragments()
    by_locator = {f.locator: f for f in fragments}
    operative = [
        by_locator["article:49a"],
        by_locator["article:49a:paragraph:1"],
        by_locator["article:49a:paragraph:2"],
        by_locator["article:49a:paragraph:3"],
    ]
    orders = [
        operative,
        list(reversed(operative)),
        [operative[2], operative[0], operative[3], operative[1]],
    ]
    outcomes: list[tuple[bool, str, str | None]] = []
    for order in orders:
        preferred = apply_structural_child_extraction_preference(
            [_decision_for(f, selected=True) for f in order],
            is_non_operative_fragment=_is_non_operative_fragment,
        )
        parent = next(d for d in preferred if d.fragment_locator == "article:49a")
        outcomes.append((parent.selected, parent.selection_reason, parent.skip_reason))
    assert len(set(outcomes)) == 1
    assert outcomes[0] == (
        False,
        SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED,
        SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    )


def test_runner_batch_selection_suppresses_49a_parent_duplicate_input() -> None:
    fragments = _load_49a_fragments()
    by_locator = {f.locator: f for f in fragments}
    source = _source_record()
    # Present jobs in shuffled order.
    jobs = [
        (source, by_locator["article:49a:paragraph:2"]),
        (source, by_locator["article:49a"]),
        (source, by_locator["article:49a:paragraph:3"]),
        (source, by_locator["article:49a:paragraph:1"]),
        (source, by_locator["document:full"]),
    ]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg={
            "required_locators": set(),
            "include_annexes": False,
            "focus_terms": [
                "minimum conservation reference size",
                "fishing vessel",
                "catch composition",
            ],
            "min_fragment_chars": 40,
        },
        fragment_selection_mode="all_matching",
    )
    by_loc = {d.fragment_locator: d for d in decisions}

    assert "article:49a" in by_loc
    assert by_loc["article:49a"].selected is False
    assert (
        by_loc["article:49a"].selection_reason
        == SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED
    )
    assert by_loc["article:49a"].skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN

    assert by_loc["article:49a:paragraph:1"].selected is True
    assert by_loc["article:49a:paragraph:2"].selected is True
    assert by_loc["article:49a:paragraph:3"].selected is True

    selected_locators = {
        d.fragment_locator for d in decisions if d.selected and d.fragment is not None
    }
    assert selected_locators == {
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
    }
    # Regression: no parent+child duplicate extraction inputs for this shape.
    assert "article:49a" not in selected_locators